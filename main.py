import os
import re
import requests
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
import subprocess
from urllib.parse import unquote
import json

# ====== CONFIG ======
api_id = 26652314
api_hash = '16e1dd8417c00068767fc6fc9a65f6b7'
target_group = -4820398082
output_folder = "Output"

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# ====== TELETHON SETUP ======
client = TelegramClient('session', api_id, api_hash)
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def log(msg):
    print(f'[🌀] {msg}')

# ====== UTILS ======
def download_file(url, filename):
    log(f'⬇️ Đang tải: {url}')
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        log(f'Lỗi tải file: {e}')
        return False

def merge_video_audio(video_path, audio_path, output_path):
    log('🔄 Ghép video + audio...')
    cmd = f'mkvmerge -o "{output_path}" "{video_path}" "{audio_path}"'
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0

# ====== PINTEREST EXTRACTOR ======
def extract_pinterest_media(pin_url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    log(f'➡ Chuyển về link gốc: {pin_url}')

    if 'pin.it' in pin_url:
        r = requests.get(pin_url, headers=headers)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, "html.parser")
            meta = soup.find("link", rel="alternate")
            if meta and 'url=' in meta['href']:
                match = re.search(r'url=(.*?)&', meta['href'])
                if match:
                    pin_url = match.group(1)
                    log(f'➡ Link gốc: {pin_url}')

    r = requests.get(pin_url, headers=headers)
    soup = BeautifulSoup(r.content, 'html.parser')

    video_tag = soup.find("video")
    if video_tag and 'src' in video_tag.attrs:
        video_url = video_tag['src']
        mp4_url = video_url.replace('/hls/', '/720p/').replace('.m3u8', '.mp4')
        return 'video', mp4_url

    img_tag = soup.find("meta", property="og:image") or soup.find("img")
    if img_tag and 'content' in img_tag.attrs:
        return 'image', img_tag['content']
    elif img_tag and 'src' in img_tag.attrs:
        return 'image', img_tag['src']

    return None, None

# ====== FACEBOOK VIDEO EXTRACTOR (via page HTML, DASH) ======
def extract_facebook_dash(link):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    try:
        resp = requests.get(link, headers=headers)
        if resp.status_code != 200:
            log("❌ Không truy cập được Facebook page")
            return None
        link = resp.url.split('?')[0]
        text = resp.text
        video_id = ''
        for part in link.split('/'):
            if part.isdigit():
                video_id = part
        try:
            target = text.split(f'"video_id":"{video_id}"')[1].split('"dash_prefetch_experimental":[')[1].split(']')[0]
        except:
            log("❌ Không phân tích được dash_prefetch")
            return None
        sources = json.loads(f'[{target}]')
        video_link = text.split(f'"representation_id":"{sources[0]}"')[1].split('"base_url":"')[1].split('"')[0].replace('\\', '')
        audio_link = text.split(f'"representation_id":"{sources[1]}"')[1].split('"base_url":"')[1].split('"')[0].replace('\\', '')
        return video_link, audio_link, video_id
    except Exception as e:
        log(f"❌ Lỗi DASH extract: {e}")
        return None

# ====== MESSAGE HANDLER ======
@client.on(events.NewMessage)
async def handler(event):
    try:
        text = event.raw_text

        # === PINTEREST ===
        if 'pinterest.com' in text or 'pin.it' in text:
            link = re.search(r'(https?://\S+)', text).group(1)
            log(f'📌 Pinterest link phát hiện: {link}')
            file_type, url = extract_pinterest_media(link)
            if not url:
                await event.reply("❌ Không tìm thấy ảnh hoặc video hợp lệ.")
                return
            filename = datetime.now().strftime("pin_%d%m%H%M%S") + ('.mp4' if file_type == 'video' else '.jpg')
            if download_file(url, filename):
                await client.send_file(target_group, filename)
                os.remove(filename)
                log(f'🧹 Đã xoá file: {filename}')
            else:
                await event.reply("❌ Lỗi khi tải hoặc gửi media từ Pinterest.")

        # === FACEBOOK DASH ===
        elif 'facebook.com' in text or 'fb.watch' in text:
            link = re.search(r'(https?://\S+)', text).group(1)
            log(f'📘 Facebook link phát hiện: {link}')
            result = extract_facebook_dash(link)
            if not result:
                await event.reply("❌ Không thể lấy video Facebook. Có thể bị chặn hoặc sai định dạng.")
                return
            video_link, audio_link, video_id = result
            video_path = os.path.join(output_folder, 'fb_video.mp4')
            audio_path = os.path.join(output_folder, 'fb_audio.mp4')
            final_path = os.path.join(output_folder, f'{video_id}.mp4')
            download_file(video_link, video_path)
            download_file(audio_link, audio_path)
            if merge_video_audio(video_path, audio_path, final_path):
                await client.send_file(target_group, final_path)
                os.remove(video_path)
                os.remove(audio_path)
                os.remove(final_path)
                log("✅ Gửi và xoá file xong")
            else:
                await event.reply("❌ Lỗi khi ghép video và audio.")

    except Exception as e:
        await event.reply(f"❌ Đã xảy ra lỗi: {e}")
        log(f'[Lỗi] {e}')

# ====== START BOT ======
with client:
    log("🤖 Bot đang chạy — xử lý link Pinterest và Facebook tự động.")
    client.run_until_disconnected()
