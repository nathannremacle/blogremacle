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
    # CORRECTION DU BUG ICI : On prépare la string AVANT de la mettre dans le f-string
    articles_list_text = "\n".join(articles[:15])
    
    prompt = f"""
    Analyse ces articles tech :
    {articles_list_text}
    
    Sélectionne le sujet le plus "Ingénierie Hardcore" (pas de gadget grand public).
    Réponds en JSON : {{ "title": "Titre FR Expert", "original_link": "url", "summary": "résumé technique", "keywords": "tags" }}
    """
    try:
        res = client.models.generate_content(model=MODEL_NAME, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json"))
        return json.loads(res.text)
    except:
        return {"title": "L'évolution des semi-conducteurs", "original_link": "https://google.com", "summary": "Analyse de la loi de Moore.", "keywords": "Hardware"}

# --- 3. AGENT RÉDACTEUR (MEGA PROMPT) ---
def write_article(topic_data):
    print(f"✍️  Rédaction Haute Qualité : {topic_data['title']}...")
    
    prompt = f"""
    Tu es un Ingénieur Senior et Rédacteur en Chef.
    Sujet : {topic_data['title']} ({topic_data['summary']}).

    OBJECTIF : Rédiger l'article de référence francophone sur ce sujet.
    Longueur : 1800 mots minimum.

    STRUCTURE OBLIGATOIRE :
    1. **Introduction Contextuelle** : Problématique actuelle, pourquoi c'est critique maintenant.
    2. **Cœur Technique (3 Sections)** : Analyse approfondie. Utilise du jargon technique précis (expliqué si besoin). Si c'est du software, mets du pseudo-code. Si c'est hardware, parle matériaux/architecture.
    3. **Implications Ingénierie** : Défis d'implémentation, coûts, scalabilité.
    4. **Conclusion Prospective** : Horizon 5-10 ans.

    CONSIGNE IMAGES (CRITIQUE) :
    Tu DOIS illustrer tes propos. Insère la balise suivante exactement là où une image aiderait la compréhension (au moins 3 fois) :
    [[IMAGE: description visuelle détaillée de ce qu'on doit voir]]

    TON :
    - Pas de "Dans cet article nous allons voir". Entre direct dans le sujet.
    - Pas de phrases creuses type "C'est une révolution". Sois factuel et analytique.
    - Utilise le Markdown (Gras, Listes, Citations).
    
    Signature finale : "Par Nathan Remacle."
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
def publish_to_hashnode(title, content, cover_url):
    print("🚀 Envoi Hashnode...")
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
            "coverImageOptions": {"coverImageURL": cover_url, "isCoverAttributionHidden": True},
            "tags": [{"slug": "engineering", "name": "Engineering"}]
        }
    }
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        data = resp.json()
        if "errors" in data:
            # Retry sans cover si erreur spécifique
            if "coverImageURL" in str(data['errors']):
                del variables["input"]["coverImageOptions"]
                resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        print(f"✅ SUCCÈS : {resp.json()['data']['publishPost']['post']['url']}")
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