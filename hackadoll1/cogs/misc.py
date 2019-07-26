import asyncio, os, pytz, requests, subprocess, time
import hkdhelper as hkd

from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from discord import Colour
from discord.ext import commands
from forex_python.converter import CurrencyRates
from googletrans import Translator
from hkdhelper import create_embed, get_html_from_url
from pycountry import countries
from random import randrange
from timezonefinder import TimezoneFinder
from urllib.parse import quote

class Misc(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config

    @commands.command(aliases=['translate'])
    async def tl(self, ctx, *, text: str):
        await ctx.channel.trigger_typing()
        await ctx.send(embed=create_embed(description=Translator().translate(text, src='ja', dest='en').text))

    @commands.command(aliases=['convert'])
    async def currency(self, ctx, *conversion: str):
        await ctx.channel.trigger_typing()
        if len(conversion) == 4 and conversion[2].lower() == 'to':
            with suppress(Exception):
                result = CurrencyRates().convert(conversion[1].upper(), conversion[3].upper(), Decimal(conversion[0]))
                await ctx.send(embed=create_embed(title='{0} {1}'.format('{:f}'.format(result).rstrip('0').rstrip('.'), conversion[3].upper())))
                return
        await ctx.send(embed=create_embed(description="Couldn't convert. Please follow this format for converting currency: **!currency** 12.34 AUD to USD.", colour=Colour.red()))

    @commands.command()
    async def weather(self, ctx, *, location: str):
        await ctx.channel.trigger_typing()
        query = location.split(',')
        if len(query) > 1:
            with suppress(Exception):
                query[1] = countries.get(name=query[1].strip().title()).alpha_2
        with suppress(Exception):
            result = requests.get('http://api.openweathermap.org/data/2.5/weather', params={ 'q': ','.join(query), 'APPID': self.config['weather_api_key'] }).json()
            timezone = pytz.timezone(TimezoneFinder().timezone_at(lat=result['coord']['lat'], lng=result['coord']['lon']))
            embed_fields = []
            embed_fields.append(('Weather', '{0}'.format(result['weather'][0]['description'].title())))
            embed_fields.append(('Temperature', '{0} °C, {1} °F'.format('{0:.2f}'.format(float(result['main']['temp']) - 273.15), '{0:.2f}'.format((1.8 * (float(result['main']['temp']) - 273.15)) + 32.0))))
            embed_fields.append(('Humidity', '{0}%'.format(result['main']['humidity'])))
            embed_fields.append(('Wind Speed', '{0} m/s'.format(result['wind']['speed'])))
            embed_fields.append(('Sunrise', '{0:%I}:{0:%M} {0:%p}'.format(datetime.fromtimestamp(result['sys']['sunrise'], tz=timezone))))
            embed_fields.append(('Sunset', '{0:%I}:{0:%M} {0:%p}'.format(datetime.fromtimestamp(result['sys']['sunset'], tz=timezone))))
            embed_fields.append(('Pressure', '{0} hPa'.format(result['main']['pressure'])))
            await ctx.send(content='**Weather for {0}, {1}**'.format(result['name'], countries.lookup(result['sys']['country']).name), embed=create_embed(fields=embed_fields, inline=True))
            return
        await ctx.send(embed=create_embed(description="Couldn't get weather. Please follow this format for checking the weather: **!weather** Melbourne, Australia.", colour=Colour.red()))

    @commands.command(aliases=['pick'])
    async def choose(self, ctx, *options: str):
        await ctx.channel.trigger_typing()
        if len(options) > 1:
            await ctx.send(embed=create_embed(description=options[randrange(len(options))]))
        else:
            await ctx.send(embed=create_embed(description='Please provide 2 or more options to choose from, e.g. **!choose** *option1* *option2*.', colour=Colour.red()))

    @commands.command(aliases=['youtube', 'play'])
    async def yt(self, ctx, *, query: str):
        await ctx.channel.trigger_typing()
        for _ in range(3):
            with suppress(Exception):
                soup = get_html_from_url('https://www.youtube.com/results?search_query={0}'.format(quote(query)))
                for result in soup.find_all(attrs={ 'class': 'yt-uix-tile-link' }):
                    link = result['href']
                    if hkd.is_youtube_link(link):
                        await ctx.send('https://www.youtube.com{0}'.format(link))
                        return
                break
        await ctx.send(embed=create_embed(title="Couldn't find any results.", colour=Colour.red()))

    @commands.command(name='dl-vid', aliases=['dlvid', 'youtube-dl', 'ytdl'])
    @commands.guild_only()
    async def dl_vid(self, ctx, url: str):
        await ctx.channel.trigger_typing()
        await ctx.send('Attempting to download the video using youtube-dl. Please wait.')
        niconico_vid = 'nicovideo.jp' in url
        ytdl_getfilename_args = ['youtube-dl']
        if niconico_vid:
            ytdl_getfilename_args += ['-u', self.config['nicovideo_user'], '-p', self.config['nicovideo_pw']]
        ytdl_getfilename_args += ['--get-filename', url]
        proc = subprocess.run(args=ytdl_getfilename_args, universal_newlines=True, stdout=subprocess.PIPE)
        vid_filename = proc.stdout.strip()
        ytdl_args = ['youtube-dl', '-o', vid_filename, '-f', 'best']
        if niconico_vid:
            ytdl_args += ['-u', self.config['nicovideo_user'], '-p', self.config['nicovideo_pw']]
        ytdl_args.append(url)
        last_try_time = time.time()
        retry = True
        while retry:
            proc = subprocess.Popen(args=ytdl_args)
            while proc.poll() is None:
                await asyncio.sleep(2)
            if proc.returncode != 0:
                if niconico_vid and time.time() - last_try_time > 30:
                    last_try_time = time.time()
                    continue
                else:
                    await ctx.send(embed=create_embed(title='Failed to download video.', colour=Colour.red()))
                    with suppress(Exception):
                        os.remove('{0}.part'.format(vid_filename))
                    return
            retry = False
        await ctx.send('Download complete. Now uploading video to Google Drive. Please wait.')
        proc = subprocess.Popen(args=['python', 'gdrive_upload.py', vid_filename, self.config['uploads_folder']])
        while proc.poll() is None:
            await asyncio.sleep(1)
        if proc.returncode != 0:
            await ctx.send(embed=create_embed(title='Failed to upload video to Google Drive.', colour=Colour.red()))
            with suppress(Exception):
                os.remove(vid_filename)
            return
        await ctx.send(content='{0.mention}'.format(ctx.author), embed=create_embed(description='Upload complete. Your video is available here: https://drive.google.com/open?id={0}. The Google Drive folder has limited space so it will be purged from time to time.'.format(self.config['uploads_folder'])))

    @commands.command(aliases=['onsenmusume'])
    async def onmusu(self, ctx, member: str=''):
        char, char_colour = hkd.WUG_ONMUSU_CHARS[hkd.parse_oshi_name(member)]
        await ctx.channel.trigger_typing()
        profile_link = 'https://onsen-musume.jp/character/{0}'.format(char)
        soup = get_html_from_url(profile_link)
        char_pic = 'https://onsen-musume.jp{0}'.format(soup.find('div', class_='character_ph__main').find('img')['src'])
        serifu = soup.find('div', class_='character_ph__serif').find('img')['alt']
        char_main = soup.find('div', class_='character_post__main')
        char_name = char_main.find('img')['alt']
        seiyuu = char_main.find('h2').find('img')['alt'][3:7]
        char_catch = char_main.find('p', class_='character_post__catch').contents[0]
        embed_fields = []
        for item in char_main.find('ul', class_='character_profile').find_all('li'):
            for i, entry in enumerate(item.find_all('span')):
                embed_fields.append((entry.contents[0], item.contents[(i + 1) * 2][1:]))
        soup = get_html_from_url('https://onsen-musume.jp/character/')
        thumbnail = 'https://onsen-musume.jp{0}'.format(soup.find('li', class_='character-list__item02 {0}'.format(char)).find('img')['src'])
        author = {}
        author['name'] = char_name
        author['url'] = profile_link
        author['icon_url'] = 'https://onsen-musume.jp/wp/wp-content/themes/onsenmusume/pc/assets/img/character/thumb/list/yu_icon.png'
        footer = {}
        footer['text'] = serifu
        await ctx.send(embed=create_embed(author=author, title='CV: {0}'.format(seiyuu), description=char_catch, colour=Colour(char_colour), image=char_pic, thumbnail=thumbnail, fields=embed_fields, footer=footer, inline=True))