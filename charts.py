from typing import List
import sekaiworld.scores as scores
import requests
from os import makedirs, path, getcwd
from selenium import webdriver
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

browser = None

def get_browser():
    global browser
    if browser is None:
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        browser = webdriver.Firefox(options=options)
    return browser


def svg_to_png(svg_path: str, png_path: str, lock: Lock):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from PIL import Image

    lock.acquire()
    browser = get_browser()
    
    # load svg
    browser.get(f'file:///{path.join(getcwd(), svg_path)}')
    
    # wait until the page is loaded, or 10s
    element = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "svg"))
    )
    
    # now that we have the preliminary stuff out of the way time to get that image :D
    element = browser.find_element(By.TAG_NAME, 'svg') # find part of the page you want image of
    location = element.location
    size = element.size
    
    left = location['x']
    top = location['y']
    right = location['x'] + size['width']
    bottom = location['y'] + size['height']
    
    # Set the window size to match the entire webpage
    browser.set_window_size(right * 1.5, bottom * 1.5)
    # take screenshot
    browser.save_screenshot(png_path)
    
    lock.release()

    im = Image.open(png_path) # uses PIL library to open image in memory

    im = im.crop((left, top, right, bottom)) # defines crop points
    im.save(png_path) # saves new cropped image
    im.close()


def render_chart(score_path: str, chart_path: str, music: dict, lock: Lock):
    # open the score from score_path and render it to a chart in chart_path
    score = scores.Score.open(score_path, encoding='utf-8')
    score.meta.title = music['title']
    score.meta.jacket = f'https://storage.sekai.best/sekai-jp-assets/music/jacket/jacket_s_{str(music['id']).zfill(3)}_rip/jacket_s_{str(music['id']).zfill(3)}.png'
    drawing = scores.Drawing(score)
    svg = drawing.svg()
    svg.saveas(chart_path)

    png_path = chart_path.replace('.svg', '.png')
    svg_to_png(chart_path, png_path, lock)


def download_score(url: str, score_path: str):
    # use requests to download the score from url and save it to score_path
    response = requests.get(url)
    response.raise_for_status()
    with open(score_path, 'wb') as file:
        file.write(response.content)


def get_list(url: str) -> List[dict]:
    # use requests to get the music list from url
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def download_and_render_score(musicDifficulty: dict):
    if musicDifficulty.get('lock', None) is None:
        raise ValueError('lock is not set in musicDifficulty')

    id: int = musicDifficulty['musicId']
    difficulty: str = musicDifficulty['musicDifficulty']
    lock: Lock = musicDifficulty['lock']
    
    print(f'Processing music id {id} with difficulty {difficulty}')
    
    # find music by id
    music = next((music for music in musics if music['id'] == id), None)
    assert music is not None, f'Music with id {id} not found'

    # pad id with loading zeros to make it 4 digits
    padId = str(id).zfill(4)
    score_url = f'https://storage.sekai.best/sekai-jp-assets/music/music_score/{padId}_01_rip/{difficulty}.txt'

    score_path = f'scores/{padId}/{musicDifficulty["musicDifficulty"]}.txt'
    makedirs(score_path.rsplit('/', 1)[0], exist_ok=True)
    download_score(score_url, score_path)
    chart_path = f'charts/{padId}/{musicDifficulty["musicDifficulty"]}.svg'
    makedirs(chart_path.rsplit('/', 1)[0], exist_ok=True)
    render_chart(score_path, chart_path, music, lock)

    print(f'Chart for music id {id} with difficulty {difficulty} saved to {chart_path}')


if __name__ == '__main__':
    musicDifficulties = get_list(
        'https://sekai-world.github.io/sekai-master-db-diff/musicDifficulties.json')
    musics = get_list(
        'https://sekai-world.github.io/sekai-master-db-diff/musics.json')
    
    lock = Lock()
    # add lock to every musicDifficulty
    for musicDifficulty in musicDifficulties:
        musicDifficulty['lock'] = lock

    with ThreadPoolExecutor() as executor:
        executor.map(download_and_render_score, musicDifficulties)
        
