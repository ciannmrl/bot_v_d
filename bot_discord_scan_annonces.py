import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import json
import os
import asyncio

# Configuration
TOKEN = os.getenv("TOKEN")  # Remplacez par votre token
CHANNEL_ID = 1499861145660686396  # Remplacez par l'ID du canal
VINTED_URL = 'https://www.vinted.fr/catalog'  # URL par défaut, modifiable
CHECK_INTERVAL = 10  # en secondes

# Fichier pour stocker les annonces vues
SEEN_ITEMS_FILE = 'seen_items.json'

intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.dm_messages = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f'Erreur de commande : {error}')

# Charger les annonces vues
def load_seen_items():
    if os.path.exists(SEEN_ITEMS_FILE):
        with open(SEEN_ITEMS_FILE, 'r') as f:
            return set(json.load(f))
    return set()

# Sauvegarder les annonces vues
def save_seen_items(seen_items):
    with open(SEEN_ITEMS_FILE, 'w') as f:
        json.dump(list(seen_items), f)

seen_items = load_seen_items()

@bot.event
async def on_ready():
    print(f'Bot connecté en tant que {bot.user}')
    check_vinted.start()

@bot.command()
async def set_url(ctx, url: str):
    global VINTED_URL
    VINTED_URL = url
    await ctx.send(f'URL Vinted mise à jour : {url}')

@bot.command(aliases=['set_id'])
async def set_channel(ctx, channel_id: int):
    global CHANNEL_ID
    CHANNEL_ID = channel_id
    await ctx.send(f'Canal mis à jour : {channel_id}')

@bot.command()
async def set_interval(ctx, interval: int):
    global CHECK_INTERVAL
    CHECK_INTERVAL = interval
    check_vinted.change_interval(seconds=interval)
    await ctx.send(f'Intervalle mis à jour : {interval} secondes')

@bot.command(name='help')
async def help_command(ctx):
    text = (
        'Commandes disponibles :\n'
        '`!set_url <url>` - Modifier l\'URL Vinted ciblée\n'
        '`!set_channel <id>` ou `!set_id <id>` - Modifier le canal de notification\n'
        '`!set_interval <secondes>` - Modifier la fréquence de vérification\n'
        '`!help` - Afficher cette aide'
    )
    await ctx.send(text)

@tasks.loop(seconds=CHECK_INTERVAL)
async def check_vinted():
    try:
        response = requests.get(VINTED_URL, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code != 200:
            print(f'Erreur HTTP {response.status_code} sur {VINTED_URL}')
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('div.new-item-box__container')
        print(f'[Vinted] {len(items)} annonces trouvées sur {VINTED_URL} (page statique, Vinted limite souvent à 96 éléments)')

        new_items = []
        for item in items:
            item_id = item.get('data-testid')
            if not item_id or item_id in seen_items:
                continue

            seen_items.add(item_id)
            link_tag = item.find('a', href=True)
            link = link_tag['href'] if link_tag else None
            if link and link.startswith('/'):
                link = f'https://www.vinted.fr{link}'
            elif not link:
                link = VINTED_URL

            title = 'Annonce Vinted'
            price = 'Prix inconnu'
            image_url = None
            img = item.find('img')
            if img:
                if img.has_attr('alt') and img['alt']:
                    alt_text = img['alt'].strip()
                    title = alt_text.split(',')[0]
                    import re
                    price_match = re.search(r'(\d+[\d ]*[\.,]?\d*\s*€)', alt_text)
                    if price_match:
                        price = price_match.group(1)
                if img.has_attr('src'):
                    image_url = img['src']
                elif img.has_attr('data-src'):
                    image_url = img['data-src']

            new_items.append({'title': title, 'price': price, 'link': link, 'image_url': image_url})

        if new_items:
            channel = bot.get_channel(CHANNEL_ID)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(CHANNEL_ID)
                except Exception as e:
                    print(f'Impossible de récupérer le canal {CHANNEL_ID}: {e}')

            if channel:
                for item in new_items:
                    embed = discord.Embed(title='Nouvelle annonce Vinted', description=item['title'], color=0x00ff00)
                    embed.add_field(name='Prix', value=item['price'], inline=True)
                    embed.add_field(name='Lien', value=item['link'], inline=False)
                    if item.get('image_url'):
                        embed.set_image(url=item['image_url'])
                    try:
                        await channel.send(embed=embed)
                    except Exception as e:
                        print(f'Erreur en envoyant le message au canal {CHANNEL_ID}: {e}')
            else:
                print(f'Canal introuvable ou inaccessible : {CHANNEL_ID}')

        save_seen_items(seen_items)

    except Exception as e:
        print(f'Erreur lors du scraping : {e}')

bot.run(TOKEN)
