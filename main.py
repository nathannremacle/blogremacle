import os
import sys
import time
import random
import requests
import feedparser
from google import genai
from google.genai import types
import json
import re
import urllib.parse
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
HASHNODE_API_URL = "https://gql.hashnode.com/"
HASHNODE_TOKEN = os.getenv("HASHNODE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Style visuel cohérent
VISUAL_STYLES = {
    "photorealistic": "macro photography, shot on Sony A7R IV, 85mm lens, f/1.8, depth of field, brushed aluminum textures, frosted glass, volumetric lighting, global illumination, raytracing, 8k, ultra-detailed",
    "blueprint": "technical isometric schematic, white thin vector lines on dark matte navy blue background, glowing accent nodes, blueprint aesthetic, minimal, clean, no background noise, architectural visualization",
}

if not HASHNODE_TOKEN or not GOOGLE_API_KEY:
    print("❌ ERREUR : Clés API manquantes.")
    sys.exit(1)

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    MODEL_NAME = "gemini-2.0-flash"
    print(f"🤖 Client Gemini initialisé : {MODEL_NAME}")
except Exception as e:
    sys.exit(1)

RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.wired.com/feed/category/science/latest/rss",
    "https://spectrum.ieee.org/feeds/topic/artificial-intelligence",
    "https://dev.to/feed/tag/engineering"
]

# --- 1. FONCTIONS IMAGES (SCRAPING & GEN) ---
def get_real_article_image(article_url):
    """Récupère l'image OG (Open Graph) officielle de l'article."""
    print(f"🕵️  Recherche image officielle sur : {article_url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(article_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                return og_image["content"]
    except Exception:
        pass
    return None

def analyze_image_relevance(image_url, topic_title):
    """Gemini juge si l'image réelle est utilisable."""
    try:
        img_data = requests.get(image_url, timeout=10).content
        from PIL import Image
        import io
        image_pil = Image.open(io.BytesIO(img_data))

        prompt = f"Est-ce une image pertinente pour un article sur '{topic_title}' (Logo, Produit, Tech) ou une image stock inutile ? Réponds GARDER ou REMPLACER."
        response = client.models.generate_content(model=MODEL_NAME, contents=[prompt, image_pil])
        return "GARDER" in response.text.upper()
    except:
        return True

def get_artistic_prompt(subject, style_key="photorealistic"):
    """Crée un prompt Midjourney-style pour Pollinations."""
    style_desc = VISUAL_STYLES.get(style_key, VISUAL_STYLES["photorealistic"])
    prompt = f"""
    Agis comme un artiste technique 3D.
    Sujet : "{subject}".
    Crée un prompt en ANGLAIS pour générer une illustration explicative.
    Focus : Matériaux nobles (verre, métal), lumière cinématique.
    Style : {style_desc}
    Sortie : Prompt brut uniquement.
    """
    try:
        return client.models.generate_content(model=MODEL_NAME, contents=prompt).text.strip()
    except:
        return f"tech illustration of {subject}, {style_desc}"

# --- REMPLACE LA FONCTION generate_ai_image PAR CELLE-CI ---
def generate_ai_image(subject, is_cover=True):
    style = "blueprint" if is_cover else "photorealistic"
    print(f"🎨 Génération IA ({style}) pour : {subject}")
    
    detailed_prompt = get_artistic_prompt(subject, style)
    encoded_prompt = urllib.parse.quote(detailed_prompt)
    seed = random.randint(0, 999999)
    
    # 1. L'URL Source (Lente et lourde)
    # On génère l'image chez Pollinations
    source_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&model=flux-realism&nologo=true"
    
    # 2. L'URL Optimisée (Rapide et légère)
    # On passe l'URL source dans le proxy 'wsrv.nl' pour la compresser
    # output=webp : Convertit en format WebP (très léger)
    # q=80 : Qualité JPEG/WebP à 80% (bon compromis)
    # url : L'adresse de l'image source encodée
    final_url = f"https://wsrv.nl/?url={urllib.parse.quote(source_url)}&output=webp&q=80"
    
    # Pause technique pour laisser le temps au serveur de génération de répondre au premier ping
    time.sleep(20)
    
    return final_url

def get_best_image_for_topic(topic_data, is_cover=True):
    """Logique Hybride : Web Réel OU IA."""
    if is_cover and topic_data.get('original_link'):
        real_url = get_real_article_image(topic_data['original_link'])
        if real_url and analyze_image_relevance(real_url, topic_data['title']):
            print("✅ Image officielle conservée.")
            return real_url
    return generate_ai_image(topic_data['title'], is_cover)

# --- 2. AGENT VEILLEUR ---
def fetch_trending_topic():
    print("🕵️  Agent Veilleur...")
    articles = []
    for feed in RSS_FEEDS:
        try:
            f = feedparser.parse(feed)
            for e in f.entries[:3]: articles.append(f"- {e.title} ({e.link})")
        except: continue
    
    random.shuffle(articles)
    
    # Préparation du texte pour éviter l'erreur de f-string backslash
    articles_list_text = "\n".join(articles[:15])
    
    prompt = f"""
    Analyse ces articles tech :
    {articles_list_text}
    
    Sélectionne le sujet le plus "Ingénierie Hardcore" (pas de gadget grand public).
    Réponds en JSON : {{ "title": "Titre FR Expert", "original_link": "url", "summary": "résumé technique", "keywords": "tags" }}
    """
    try:
        res = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt, 
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(res.text)
        
        # --- FIX DU BUG "TypeError: list indices..." ---
        if isinstance(data, list):
            if len(data) > 0:
                return data[0]
            else:
                raise ValueError("Liste JSON vide reçue de l'IA")
        
        return data
        
    except Exception as e:
        print(f"⚠️ Erreur ou Fallback activé : {e}")
        return {
            "title": "L'avenir des semi-conducteurs", 
            "original_link": "https://google.com", 
            "summary": "Analyse technique des limites physiques actuelles.", 
            "keywords": "Hardware"
        }

# --- 3. AGENT RÉDACTEUR (MEGA PROMPT) ---
def write_article(topic_data):
    print(f"✍️  Rédaction SEO Haute Qualité : {topic_data['title']}...")
    
    # IMPORTANT : Remplace par ton vrai sous-domaine
    MON_BLOG_URL = "https://remacle.hashnode.dev"
    
    prompt = f"""
    Tu es un Ingénieur Senior et Expert SEO.
    Sujet : {topic_data['title']}
    Contexte : {topic_data['summary']}

    OBJECTIF : Rédiger l'article de référence (1800 mots).

    OPTIMISATION SEO ON-PAGE (OBLIGATOIRE) :
    1. Choisis un **Mot-Clé Principal** lié au sujet.
    2. Utilise ce mot-clé dans le premier paragraphe.
    3. Utilise des variantes sémantiques dans les titres H2.

    RÈGLES STRICTES :
    1. Commence DIRECTEMENT par le contenu. Pas de "Voici l'article" ni "Titre :".
    2. Utilise le Markdown (## Titres) et pas "H2:".
    3. Insère la balise [[IMAGE: description détaillée]] au moins 3 fois.

    STRUCTURE :
    1. Introduction (Sans le mot "Introduction" comme titre)
    2. Cœur Technique (3 sections ##)
    3. Conclusion
    4. Appel à l'action : "--- \n Pour approfondir, visitez le [Blog]({MON_BLOG_URL})."
    
    TON : Expert, factuel, analytique.
    Signature : "Par Nathan Remacle."
    """
    try:
        return client.models.generate_content(model=MODEL_NAME, contents=prompt).text
    except:
        sys.exit(1)

# --- 4. AGENT CORRECTEUR (IA) ---
def verify_and_clean_article(content):
    print("👮 Agent Correcteur IA : Vérification...")
    prompt = f"""
    Agis comme un compilateur de code.
    Entrée : Un article de blog.
    Tâche : Supprimer tout texte conversationnel (ex: "Voici l'article", "Absolument", "Titre:").
    Corriger le formatage Markdown des titres (ex: "H2 :" -> "## ").
    
    SI le texte est déjà propre, renvoie-le tel quel.
    SINON, renvoie UNIQUEMENT le texte nettoyé.
    
    TEXTE :
    {content}
    """
    try:
        # Température 0 pour être robotique
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
        return res.text.strip()
    except: return content

# --- 5. NETTOYEUR ULTIME (PYTHON REGEX) ---
def final_force_clean(content):
    """
    C'est la sécurité finale. Même si l'IA se trompe, ce code Python
    va brutalement nettoyer les erreurs connues.
    """
    print("🧹 Nettoyage Python Final (Karcher)...")
    
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # 1. Supprime les phrases de politesse IA résiduelles
        if any(bad_start in line for bad_start in ["Voici une version", "Absolument !", "Sure, here", "Here is the"]):
            continue
            
        # 2. Supprime les labels explicites type "Titre :" ou "Introduction :"
        line = re.sub(r'^(Titre|Title|Introduction|Conclusion)\s*:\s*', '', line)
        
        # 3. Corrige les "H2 :" ou "H2:" ou "**H2** :" en "## "
        line = re.sub(r'^(\*\*|)?(H[1-6]|h[1-6])(\*\*|)?\s*:\s*', '## ', line)
        
        cleaned_lines.append(line)
    
    return "\n".join(cleaned_lines).strip()

# --- 6. LOGIQUE DE PLACEMENT INTELLIGENT ---
def smart_insert_images(content, topic_title):
    # Remplacement des balises existantes
    if "[[IMAGE:" in content:
        def replace_tag(match):
            desc = match.group(1)
            url = generate_ai_image(desc, is_cover=False)
            return f"\n\n![Figure: {desc}]({url})\n*Figure : {desc}*\n"
        return re.sub(r'\[\[IMAGE: (.*?)\]\]', replace_tag, content)

    # Fallback si IA a oublié
    print("⚠️ Injection images forcée...")
    lines = content.split('\n')
    new_content = []
    img_count = 0
    for line in lines:
        new_content.append(line)
        if line.startswith("## ") and img_count < 3:
            section = line.replace("#", "").strip()
            url = generate_ai_image(f"Tech diagram: {section} context {topic_title}", is_cover=False)
            new_content.append(f"\n\n![Schéma: {section}]({url})\n*Figure : {section}*\n")
            img_count += 1
    return "\n".join(new_content)

# --- 7. SEO ET PUBLICATION ---
def generate_seo_data(content, title):
    print("🔍 Optimisation SEO en cours...")
    prompt = f"""
    Agis comme un expert SEO.
    Titre : {title}
    Début : {content[:500]}...

    Génère JSON (sans markdown) :
    1. "slug": URL courte, minuscules, tirets (ex: "puce-nvidia").
    2. "meta_title": Titre Google (< 60 car).
    3. "meta_description": Résumé (< 155 car).
    """
    try:
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
        
        # --- CORRECTIF APPLIQUÉ ICI ---
        # Si Gemini renvoie une liste [{...}], on prend le premier élément
        if isinstance(data, list):
            if len(data) > 0:
                return data[0]
            else:
                raise ValueError("Liste SEO vide reçue")
        
        return data
        
    except Exception as e:
        # Fallback de secours en cas d'erreur
        from unicodedata import normalize
        # Création manuelle du slug
        slug = title.lower().replace(" ", "-")
        slug = re.sub(r'[^a-z0-9-]', '', normalize('NFKD', slug).encode('ASCII', 'ignore').decode('utf-8'))
        
        return {
            "slug": slug[:50], 
            "meta_title": title[:60], 
            "meta_description": content[:150] + "..."
        }

def publish_to_hashnode(title, content, cover_url):
    print("🚀 Envoi Hashnode avec SEO...")
    
    seo_data = generate_seo_data(content, title)
    
    query_pub = """query { me { publications(first: 1) { edges { node { id } } } } }"""
    headers = {"Authorization": f"Bearer {HASHNODE_TOKEN}", "Content-Type": "application/json"}
    
    try:
        pub_id = requests.post(HASHNODE_API_URL, json={"query": query_pub}, headers=headers).json()['data']['me']['publications']['edges'][0]['node']['id']
    except: sys.exit(1)

    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) { post { url } }
    }
    """
    
    variables = {
        "input": {
            "title": title,
            "contentMarkdown": content,
            "publicationId": pub_id,
            "slug": seo_data['slug'],
            "metaTags": {
                "title": seo_data['meta_title'],
                "description": seo_data['meta_description'],
                "image": cover_url
            },
            "coverImageOptions": {"coverImageURL": cover_url, "isCoverAttributionHidden": True},
            "tags": [{"slug": "engineering", "name": "Engineering"}, {"slug": "technology", "name": "Technology"}]
        }
    }
    
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        data = resp.json()
        if "errors" in data:
            print(f"⚠️ Erreur Hashnode : {data['errors']}")
            if "coverImageURL" in str(data['errors']):
                del variables["input"]["coverImageOptions"]
                resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        
        if 'data' in resp.json() and resp.json()['data']['publishPost']:
            print(f"✅ SUCCÈS : {resp.json()['data']['publishPost']['post']['url']}")
        else:
            print("⚠️ Article publié mais URL non récupérée.")
            
    except Exception as e:
        print(f"❌ Erreur: {e}")

# --- MAIN ---
def main():
    # 1. Sujet
    topic = fetch_trending_topic()
    print(f"🎯 Sujet : {topic['title']}")
    
    # 2. Cover (Hybride)
    cover_url = get_best_image_for_topic(topic, is_cover=True)
    
    # 3. Rédaction (IA Créative)
    draft_content = write_article(topic)
    
    # 4. Correction (IA Éditoriale - NOUVEAU)
    cleaned_draft = verify_and_clean_article(draft_content)

    # 5. Nettoyage Final (Python Karcher - NOUVEAU)
    final_text_only = final_force_clean(cleaned_draft)
    
    # 6. Injection Intelligente des Images (Sur texte propre)
    final_content = smart_insert_images(final_text_only, topic['title'])
    
    # 7. Publication
    publish_to_hashnode(topic['title'], final_content, cover_url)

if __name__ == "__main__":

    main()
