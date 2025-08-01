import os
import re
import requests
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from telethon import TelegramClient, events
import subprocess
from urllib.parse import unquote

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

# ====== FACEBOOK VIDEO EXTRACTOR (via mbasic) ======
def extract_facebook_video_links(fb_url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    log(f'➡ Xử lý Facebook URL qua mbasic: {fb_url}')
    try:
        mbasic_url = fb_url.replace("facebook.com", "mbasic.facebook.com")
        resp = requests.get(mbasic_url, headers=headers, timeout=5, allow_redirects=True)
        if resp.status_code != 200:
            log("❌ Không thể truy cập mbasic.facebook.com")
            return None, None
        matches = re.findall(r'/video_redirect/\?src=(.*?)"', resp.text)
        if not matches:
            log("❌ Không tìm thấy link video từ mbasic.")
            return None, None
        video_url = unquote(matches[0])
        return video_url, None
    except Exception as e:
        log(f'❌ Lỗi khi lấy link video mbasic: {e}')
        return None, None

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

        # === FACEBOOK ===
        elif 'facebook.com' in text or 'fb.watch' in text:
            link = re.search(r'(https?://\S+)', text).group(1)
            log(f'📘 Facebook link phát hiện: {link}')
            video_url, _ = extract_facebook_video_links(link)
            if not video_url:
                await event.reply("❌ Không tìm thấy video Facebook hợp lệ. Có thể do quyền riêng tư hoặc không công khai.")
                return
            video_path = os.path.join(output_folder, "fb_{}.mp4".format(datetime.now().strftime("%d%m%H%M%S")))
            if download_file(video_url, video_path):
                await client.send_file(target_group, video_path, caption="📽 Video từ Facebook")
                os.remove(video_path)
            else:
                await event.reply("❌ Lỗi khi tải video Facebook.")

    except Exception as e:
        await event.reply(f"❌ Đã xảy ra lỗi: {e}")
        log(f'[Lỗi] {e}')

# ====== START BOT ======
with client:
    log("🤖 Bot đang chạy — xử lý link Pinterest và Facebook tự động.")
    client.run_until_disconnected()
