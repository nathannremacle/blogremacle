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

# --- CONFIGURATION ---
HASHNODE_API_URL = "https://gql.hashnode.com/"
HASHNODE_TOKEN = os.getenv("HASHNODE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Style visuel
BLOG_VISUAL_THEME = "minimalist vector art, engineering blueprint style, orange and dark grey color palette, high quality, 8k, unreal engine 5 render"

if not HASHNODE_TOKEN or not GOOGLE_API_KEY:
    print("❌ ERREUR : Clés API manquantes.")
    sys.exit(1)

# --- INITIALISATION NOUVEAU SDK (v2) ---
try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    # On garde le modèle Flash pour la rapidité
    MODEL_NAME = "gemini-2.0-flash"
    print(f"🤖 Client Gemini initialisé sur le modèle : {MODEL_NAME}")
except Exception as e:
    print(f"❌ Erreur lors de l'initialisation du client Gemini : {e}")
    sys.exit(1)

# --- LISTE DES SOURCES ---
RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.wired.com/feed/category/science/latest/rss",
    "https://spectrum.ieee.org/feeds/topic/artificial-intelligence",
    "https://dev.to/feed/tag/engineering"
]

# --- AGENT 1 : LE VEILLEUR ---
def fetch_trending_topic():
    print("🕵️  Agent Veilleur : Scan des flux RSS...")
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                articles.append(f"- {entry.title} (Link: {entry.link})")
        except Exception as e:
            print(f"⚠️ Erreur lecture flux {feed_url}: {e}")
    
    random.shuffle(articles)
    context_articles = "\n".join(articles[:15])

    prompt = f"""
    Tu es un rédacteur en chef expert en ingénierie. Voici une liste d'articles récents :
    {context_articles}

    Sélectionne le sujet le plus pertinent.
    Réponds UNIQUEMENT avec un objet JSON valide :
    {{
        "title": "Titre accrocheur en Français",
        "original_link": "Lien source",
        "summary": "Résumé en 3 phrases",
        "keywords": "mots clés"
    }}
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Erreur Agent Veilleur : {e}")
        # Fallback en cas d'erreur JSON
        return {
            "title": "L'avenir de l'IA générative en ingénierie",
            "original_link": "https://google.com",
            "summary": "Une analyse des tendances actuelles.",
            "keywords": "AI, Engineering"
        }

# --- AGENT 2 : L'ARTISTE ---
def generate_image(prompt_description, is_cover=True):
    print(f"🎨 Agent Artiste : Création de l'image ({'Cover' if is_cover else 'Inline'})...")
    
    full_prompt = f"{prompt_description}, {BLOG_VISUAL_THEME}, no text, cinematic lighting"
    encoded_prompt = requests.utils.quote(full_prompt)
    seed = random.randint(0, 999999)
    
    # ASTUCE : On ajoute ".jpg" à la fin du path pour que Hashnode reconnaisse que c'est une image
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}.jpg?width=1280&height=720&seed={seed}&model=flux&nologo=true"
    
    # Pour les images internes, on ne valide pas pour gagner du temps, on renvoie direct
    if not is_cover:
        return image_url 

    # Validation pour la Cover uniquement
    print("🧐 Agent Critique : Vérification de la qualité de l'image...")
    try:
        # On télécharge l'image pour "chauffer" le cache Pollinations et vérifier qu'elle existe
        resp = requests.get(image_url)
        if resp.status_code != 200:
            raise Exception("Image non accessible")
            
        img_data = resp.content
        from PIL import Image
        import io
        image_pil = Image.open(io.BytesIO(img_data))

        validation_prompt = "Cette image est-elle une illustration abstraite ou technique correcte ? Réponds OUI ou NON."
        validation = client.models.generate_content(
            model=MODEL_NAME,
            contents=[validation_prompt, image_pil]
        )
        
        if "NON" in validation.text.upper() and "PAS" in validation.text.upper():
             # Retry simple si vraiment mauvais
            print("⚠️ Image rejetée. Nouvelle tentative...")
            seed2 = random.randint(0, 999999)
            return f"https://image.pollinations.ai/prompt/{encoded_prompt}.jpg?width=1280&height=720&seed={seed2}&model=flux&nologo=true"
        
        print("✅ Image validée.")
        return image_url

    except Exception as e:
        print(f"⚠️ Warning validation image ({e}), utilisation telle quelle.")
        return image_url

# --- AGENT 3 : LE RÉDACTEUR ---
def write_article(topic_data):
    print(f"✍️  Agent Rédacteur : Rédaction sur '{topic_data['title']}'...")
    
    prompt = f"""
    Rédige un article de blog technique (min 1500 mots) en Français sur :
    Titre : {topic_data['title']}
    Source : {topic_data['summary']}
    
    CONSIGNES DE FORMATAGE (TRES IMPORTANT) :
    1. Utilise le Markdown standard.
    2. Insère OBLIGATOIREMENT 2 images dans le texte.
    3. Pour insérer une image, utilise UNIQUEMENT cette syntaxe spéciale :
       [[IMAGE: description visuelle courte en anglais]]
       
    Exemple : Voici un paragraphe...
    [[IMAGE: futuristic server room blueprint]]
    Voici la suite...
    
    Finis par : "Rédigé par Nathan Remacle."
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ Erreur Agent Rédacteur : {e}")
        sys.exit(1)

# --- PUBLICATION HASHNODE ---
def publish_to_hashnode(title, content, cover_image_url):
    print("🚀 Publication sur Hashnode...")
    print(f"DEBUG: Cover URL envoyée : {cover_image_url}")
    
    query_pub = """query { me { publications(first: 1) { edges { node { id } } } } }"""
    headers = {"Authorization": f"Bearer {HASHNODE_TOKEN}", "Content-Type": "application/json"}
    
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": query_pub}, headers=headers)
        pub_id = resp.json()['data']['me']['publications']['edges'][0]['node']['id']
    except Exception as e:
        print(f"❌ Erreur ID Hashnode : {e}")
        sys.exit(1)

    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post { url }
      }
    }
    """
    variables = {
        "input": {
            "title": title,
            "contentMarkdown": content,
            "publicationId": pub_id,
            "coverImageOptions": {
                "coverImageURL": cover_image_url,
                "isCoverAttributionHidden": True
            },
            "tags": [{"slug": "engineering", "name": "Engineering"}, {"slug": "technology", "name": "Technology"}]
        }
    }
    
    try:
        resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
        resp_json = resp.json()
        
        if "errors" in resp_json:
            print("❌ Erreur Hashnode:", resp_json['errors'])
            # On tente sans l'image de couverture si ça plante à cause de ça
            if "coverImageURL" in str(resp_json['errors']):
                print("⚠️ Tentative de republication SANS image de couverture...")
                del variables["input"]["coverImageOptions"]
                resp = requests.post(HASHNODE_API_URL, json={"query": mutation, "variables": variables}, headers=headers)
                print(f"✅ Article publié (sans cover) : {resp.json()['data']['publishPost']['post']['url']}")
            else:
                sys.exit(1)
        else:
            print(f"✅ Article publié AVEC succès : {resp_json['data']['publishPost']['post']['url']}")
            
    except Exception as e:
        print(f"❌ Erreur Publication : {e}")
        sys.exit(1)

# --- MAIN ---
def main():
    topic = fetch_trending_topic()
    print(f"🎯 Sujet : {topic['title']}")
    
    # 1. Génération Cover
    cover_url = generate_image(f"Editorial illustration for '{topic['title']}'", is_cover=True)
    
    # 2. Rédaction
    raw_content = write_article(topic)
    
    # 3. Remplacement des images (Logique plus robuste)
    # On cherche [[IMAGE: ...]] ou ![IMG_PROMPT: ...] ou [IMG: ...]
    # Regex souple qui capture tout ce qui ressemble à un tag d'image
    pattern = r'\[\[IMAGE: (.*?)\]\]|!\[IMG_PROMPT: (.*?)\]|\[IMG: (.*?)\]'
    
    def replace_match(match):
        # On récupère le groupe qui n'est pas None (car il y a 3 groupes dans le regex)
        prompt = next((g for g in match.groups() if g is not None), "technology abstract")
        print(f"🖼️  Génération image interne : {prompt}")
        url = generate_image(prompt, is_cover=False)
        return f"![{prompt}]({url})"
    
    final_content, num_subs = re.subn(pattern, replace_match, raw_content)
    print(f"📊 Nombre d'images insérées : {num_subs}")

    # SECURITY CHECK : Si aucune image n'a été insérée par l'IA, on en force une après le 1er paragraphe
    if num_subs == 0:
        print("⚠️ Aucune image détectée dans le texte généré. Insertion forcée.")
        forced_url = generate_image(f"Diagram describing {topic['title']}", is_cover=False)
        # On insère après le premier double saut de ligne
        parts = final_content.split("\n\n", 1)
        if len(parts) > 1:
            final_content = parts[0] + f"\n\n![Illustration Principale]({forced_url})\n\n" + parts[1]
        else:
            final_content = f"![Illustration]({forced_url})\n\n" + final_content

    # 4. Publication
    publish_to_hashnode(topic['title'], final_content, cover_url)

if __name__ == "__main__":
    main()