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
from bs4 import BeautifulSoup  # NÉCESSAIRE POUR LE SCRAPING

# --- CONFIGURATION ---
HASHNODE_API_URL = "https://gql.hashnode.com/"
HASHNODE_TOKEN = os.getenv("HASHNODE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Style AI (Fallback)
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

# --- FONCTION : RÉCUPÉRER L'IMAGE RÉELLE (SCRAPING) ---
def get_real_article_image(article_url):
    """
    Tente de récupérer l'image 'Open Graph' officielle de l'article source.
    """
    print(f"🕵️  Tentative de récupération de l'image réelle sur : {article_url}")
    try:
        # On se fait passer pour un navigateur classique pour ne pas être bloqué
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(article_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Recherche de la balise og:image (Standard Facebook/LinkedIn)
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                real_url = og_image["content"]
                print(f"✅ Image officielle trouvée : {real_url}")
                return real_url
                
            # Fallback : Twitter image
            twitter_image = soup.find("meta", name="twitter:image")
            if twitter_image and twitter_image.get("content"):
                return twitter_image["content"]
                
    except Exception as e:
        print(f"⚠️ Impossible de scrapper l'image réelle : {e}")
    
    return None

# --- FONCTION : ANALYSE D'IMAGE PAR GEMINI ---
def analyze_image_relevance(image_url, topic_title):
    """
    Demande à Gemini si l'image réelle est bonne ou si on doit la remplacer.
    """
    print("🧐 Juge IA : Analyse de la pertinence de l'image réelle...")
    try:
        # Téléchargement temporaire
        img_data = requests.get(image_url, timeout=10).content
        from PIL import Image
        import io
        image_pil = Image.open(io.BytesIO(img_data))

        prompt = f"""
        Regarde cette image extraite d'un article intitulé "{topic_title}".
        
        Est-ce une image pertinente et de bonne qualité (Logo officiel, Photo du produit, Diagramme clair) ?
        Ou est-ce une image générique inutile / stock photo de mauvaise qualité ?
        
        Réponds UNIQUEMENT par 'GARDER' ou 'REMPLACER'.
        """
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, image_pil]
        )
        
        decision = response.text.strip().upper()
        print(f"🤖 Verdict IA : {decision}")
        return "GARDER" in decision
        
    except Exception as e:
        print(f"⚠️ Erreur analyse image ({e}), on garde par défaut.")
        return True

# --- AGENT VEILLEUR ---
def fetch_trending_topic():
    print("🕵️  Agent Veilleur : Recherche de sujets...")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                articles.append(f"- {entry.title} (Link: {entry.link})")
        except Exception:
            continue
    
    random.shuffle(articles)
    context_articles = "\n".join(articles[:15])

    prompt = f"""
    Tu es rédacteur en chef Tech. Analyse ces titres :
    {context_articles}

    Choisis le meilleur sujet technique.
    Réponds en JSON uniquement :
    {{
        "title": "Titre Français Expert",
        "original_link": "L'URL EXACTE fournie dans la liste (très important)",
        "summary": "Résumé technique",
        "keywords": "tags"
    }}
    """
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception:
        # Fallback hardcodé si échec JSON
        return {
            "title": "Nouvelle avancée en calcul quantique",
            "original_link": "https://www.wired.com",
            "summary": "Le calcul quantique franchit une étape.",
            "keywords": "Quantum"
        }

# --- AGENT ARTISTIQUE (GÉNÉRATION SEULEMENT SI NÉCESSAIRE) ---
def get_artistic_prompt(subject, style_key="photorealistic"):
    style_desc = VISUAL_STYLES.get(style_key, VISUAL_STYLES["photorealistic"])
    prompt = f"""
    Agis comme un photographe d'art 3D.
    Sujet : "{subject}".
    Crée un prompt pour générer une image ABSTRAITE et TECHNIQUE.
    Concentre-toi sur : textures (verre, métal), lumière volumétrique, 8k.
    Style : {style_desc}
    Prompt ANGLAIS brut uniquement.
    """
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        return response.text.strip()
    except:
        return f"futuristic tech, {style_desc}"

def generate_ai_image(subject, is_cover=True):
    style = "blueprint" if is_cover else "photorealistic"
    print(f"🎨 Génération IA nécessaire ({style})...")
    
    detailed_prompt = get_artistic_prompt(subject, style)
    encoded_prompt = urllib.parse.quote(detailed_prompt)
    seed = random.randint(0, 999999)
    
    # On utilise Flux Realism
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&model=flux-realism&nologo=true"
    time.sleep(2)
    return image_url + "&.jpg" # Fake extension pour Hashnode

# --- MAIN LOGIC ---
def get_best_image_for_topic(topic_data, is_cover=True):
    """
    Logique Hybride :
    1. Essayer de trouver l'image réelle de l'article.
    2. La faire valider par l'IA.
    3. Sinon, générer une image IA.
    """
    real_image_url = None
    
    # Seulement pour la couverture, on cherche l'image réelle
    if is_cover and 'original_link' in topic_data and topic_data['original_link'].startswith('http'):
        real_image_url = get_real_article_image(topic_data['original_link'])
    
    if real_image_url:
        # On demande à l'IA si l'image vaut le coup
        is_good = analyze_image_relevance(real_image_url, topic_data['title'])
        if is_good:
            print(f"✅ Décision : Utilisation de l'image OFFICIELLE du web.")
            return real_image_url
        else:
            print(f"❌ Décision : L'image réelle est mauvaise. Passage à la génération IA.")
    
    # Si pas d'image réelle ou rejetée -> Génération IA
    return generate_ai_image(topic_data['title'], is_cover)

# --- REDACTION & PUBLICATION (Inchangé sauf appel image) ---
def write_article(topic_data):
    print(f"✍️  Rédaction : {topic_data['title']}...")
    prompt = f"""
    Rédige un article expert (1500 mots) sur : {topic_data['title']}.
    Source : {topic_data['summary']}
    
    Consignes : Markdown, H2/H3, Ton Pro.
    Inclus 2 images avec ce tag EXACT : [[IMAGE: description courte]]
    Signature : "Rédigé par Nathan Remacle."
    """
    try:
        return client.models.generate_content(model=MODEL_NAME, contents=prompt).text
    except:
        sys.exit(1)

def publish_to_hashnode(title, content, cover_url):
    print(f"🚀 Publication vers Hashnode (Cover: {cover_url})...")
    # ... (Code publication identique à précedemment) ...
    # Je remets le bloc de publication standard pour la complétude
    query_pub = """query { me { publications(first: 1) { edges { node { id } } } } }"""
    headers = {"Authorization": f"Bearer {HASHNODE_TOKEN}", "Content-Type": "application/json"}
    try:
        pub_id = requests.post(HASHNODE_API_URL, json={"query": query_pub}, headers=headers).json()['data']['me']['publications']['edges'][0]['node']['id']
    except:
        sys.exit(1)

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
        print(f"✅ SUCCÈS : {resp.json()['data']['publishPost']['post']['url']}")
    except Exception as e:
        print(f"❌ Erreur publication : {e}")

# --- ORCHESTRATION ---
def main():
    topic = fetch_trending_topic()
    print(f"🎯 Sujet : {topic['title']}")
    
    # 1. COVER : Hybride (Web Réel ou IA)
    cover_url = get_best_image_for_topic(topic, is_cover=True)
    
    # 2. REDACTION
    raw_content = write_article(topic)
    
    # 3. IMAGES INTERNES : Toujours IA (plus simple pour le contexte spécifique)
    def replace_img(match):
        desc = match.group(1)
        url = generate_ai_image(desc, is_cover=False)
        return f"![Illustration: {desc}]({url})"
    
    final_content = re.sub(r'\[\[IMAGE: (.*?)\]\]', replace_img, raw_content)
    
    # Sécurité image interne
    if "![Illustration" not in final_content:
        forced_img = generate_ai_image(f"Diagram for {topic['title']}", is_cover=False)
        final_content = f"![Main Illustration]({forced_img})\n\n" + final_content

    publish_to_hashnode(topic['title'], final_content, cover_url)

if __name__ == "__main__":
    main()