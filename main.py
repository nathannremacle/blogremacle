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

def generate_ai_image(subject, is_cover=True):
    style = "blueprint" if is_cover else "photorealistic"
    print(f"🎨 Génération IA ({style}) pour : {subject}")
    
    detailed_prompt = get_artistic_prompt(subject, style)
    encoded_prompt = urllib.parse.quote(detailed_prompt)
    seed = random.randint(0, 999999)
    
    # Flux Realism pour la qualité texture
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&model=flux-realism&nologo=true"
    time.sleep(2)
    return url + "&.jpg"

def get_best_image_for_topic(topic_data, is_cover=True):
    """Logique Hybride : Web Réel OU IA."""
    if is_cover and topic_data.get('original_link'):
        real_url = get_real_article_image(topic_data['original_link'])
        if real_url and analyze_image_relevance(real_url, topic_data['title']):
            print("✅ Image officielle conservée.")
            return real_url
    return generate_ai_image(topic_data['title'], is_cover)

# --- 2. AGENT VEILLEUR (CORRIGÉ) ---
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
        # Si Gemini renvoie une liste [{...}], on prend le premier élément.
        if isinstance(data, list):
            if len(data) > 0:
                return data[0]
            else:
                # Si la liste est vide, on force une erreur pour déclencher le fallback
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
    
    prompt = f"""
    Tu es un Ingénieur Senior et Expert SEO.
    Sujet : {topic_data['title']}
    Contexte : {topic_data['summary']}

    OBJECTIF : Rédiger l'article de référence (1800 mots).

    OPTIMISATION SEO ON-PAGE (OBLIGATOIRE) :
    1. Choisis un **Mot-Clé Principal** lié au sujet.
    2. Utilise ce mot-clé dans le premier paragraphe (les 100 premiers mots).
    3. Utilise des variantes sémantiques dans les titres H2.
    4. Pour les images, sois descriptif dans le Alt Text (ex: "Schéma technique du processeur ARM" et pas juste "Processeur").

    STRUCTURE :
    1. **Introduction** : Accroche directe, définition du problème, mot-clé principal.
    2. **Cœur Technique (3-4 Sections)** : Analyse profonde, jargon expliqué, comparaisons.
    3. **Conclusion** : Synthèse et ouverture.

    CONSIGNE IMAGES :
    Insère cette balise 3 fois aux moments clés :
    [[IMAGE: description visuelle précise pour un diagramme technique]]

    TON : Expert, factuel, analytique. Pas de blabla commercial.
    Signature : "Par Nathan Remacle."
    """
    try:
        return client.models.generate_content(model=MODEL_NAME, contents=prompt).text
    except:
        sys.exit(1)

# --- 4. LOGIQUE DE PLACEMENT INTELLIGENT ---
def smart_insert_images(content, topic_title):
    """
    Si l'IA a oublié les balises, on découpe le texte par chapitres (H2) 
    et on insère des images contextuelles.
    """
    # 1. Si des balises existent déjà, on les traite
    if "[[IMAGE:" in content:
        def replace_tag(match):
            desc = match.group(1)
            url = generate_ai_image(desc, is_cover=False)
            return f"\n\n![Illustration: {desc}]({url})\n*Figure : {desc}*\n"
        
        new_content = re.sub(r'\[\[IMAGE: (.*?)\]\]', replace_tag, content)
        return new_content

    # 2. SINON (Fallback Intelligent) : On cherche les titres H2 (##)
    print("⚠️ Pas de balises images trouvées. Activation de l'injection intelligente...")
    
    lines = content.split('\n')
    final_lines = []
    images_inserted = 0
    
    for line in lines:
        final_lines.append(line)
        
        # Si on détecte un titre H2 (ex: "## 1. Architecture du Processeur")
        # On insère une image JUSTE APRÈS le paragraphe suivant ce titre (pour pas casser le flux)
        if line.strip().startswith("## ") and images_inserted < 3:
            # On nettoie le titre pour en faire un prompt
            section_title = line.replace("#", "").strip()
            img_prompt = f"Technical diagram showing {section_title} in the context of {topic_title}"
            
            # On génère l'URL
            url = generate_ai_image(img_prompt, is_cover=False)
            
            # On ajoute l'image Markdown
            image_block = f"\n\n![Schéma : {section_title}]({url})\n*Figure : {section_title}*\n"
            final_lines.append(image_block)
            images_inserted += 1
            
    return "\n".join(final_lines)

# --- 5. PUBLICATION ---

def generate_seo_data(content, title):
    """
    Analyse l'article rédigé et génère les métadonnées pour Google.
    """
    print("🔍 Optimisation SEO en cours...")
    prompt = f"""
    Agis comme un expert SEO (Search Engine Optimization).
    Voici un article de blog :
    Titre : {title}
    Début du contenu : {content[:500]}...

    Génère un objet JSON (sans markdown) avec ces 3 champs optimisés pour le référencement :
    1. "slug": Une URL courte, en minuscules, avec des tirets, sans accents (ex: "nouvelle-puce-nvidia-revolution").
    2. "meta_title": Un titre pour Google (< 60 caractères), percutant, incluant le mot-clé principal.
    3. "meta_description": Un résumé incitatif pour le clic (< 155 caractères), sans jargon excessif.

    Réponds UNIQUEMENT le JSON.
    """
    try:
        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except:
        # Fallback basique si l'IA échoue
        from unicodedata import normalize
        slug = title.lower().replace(" ", "-")
        slug = re.sub(r'[^a-z0-9-]', '', normalize('NFKD', slug).encode('ASCII', 'ignore').decode('utf-8'))
        return {
            "slug": slug[:50],
            "meta_title": title[:60],
            "meta_description": content[:150] + "..."
        }

def publish_to_hashnode(title, content, cover_url):
    print("🚀 Envoi Hashnode avec SEO...")
    
    # 1. Génération des données SEO
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
            # --- SEO : NOUVEAUX CHAMPS ---
            "slug": seo_data['slug'],
            "metaTags": {
                "title": seo_data['meta_title'],
                "description": seo_data['meta_description'],
                "image": cover_url
            },
            # -----------------------------
            "coverImageOptions": {"coverImageURL": cover_url, "isCoverAttributionHidden": True},
            "tags": [
                {"slug": "engineering", "name": "Engineering"},
                {"slug": "technology", "name": "Technology"}
            ]
        }
    }
    
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        data = resp.json()
        if "errors" in data:
            print(f"⚠️ Erreur Hashnode : {data['errors']}")
            # Retry sans cover si erreur spécifique à l'image
            if "coverImageURL" in str(data['errors']):
                del variables["input"]["coverImageOptions"]
                resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        
        # On sécurise l'affichage du succès
        if 'data' in resp.json() and resp.json()['data']['publishPost']:
            print(f"✅ SUCCÈS : {resp.json()['data']['publishPost']['post']['url']}")
        else:
            print("⚠️ Article publié mais URL non récupérée (Erreur partielle).")
            
    except Exception as e:
        print(f"❌ Erreur: {e}")

# --- MAIN ---
def main():
    # 1. Sujet
    topic = fetch_trending_topic()
    print(f"🎯 Sujet : {topic['title']}")
    
    # 2. Cover (Hybride)
    cover_url = get_best_image_for_topic(topic, is_cover=True)
    
    # 3. Rédaction
    raw_content = write_article(topic)
    
    # 4. Injection Intelligente des Images
    final_content = smart_insert_images(raw_content, topic['title'])
    
    # 5. Publication
    publish_to_hashnode(topic['title'], final_content, cover_url)

if __name__ == "__main__":
    main()