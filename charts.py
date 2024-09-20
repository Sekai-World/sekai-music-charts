from concurrent.futures import ThreadPoolExecutor
from os import getcwd, makedirs, path
from selenium import webdriver
from threading import Lock
from typing import List, Tuple
import requests
import sekaiworld.scores as scores

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


def render_chart(score_path: str, chart_path: str, music: dict, jacket: str, lock: Lock):
    # open the score from score_path and render it to a chart in chart_path
    score = scores.Score.open(score_path, encoding='utf-8')
    score.meta.title = music['title']
    score.meta.jacket = jacket
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


def download_and_render_score(musicInfo: Tuple[dict, dict]):
    music, musicDifficulty = musicInfo
    if musicDifficulty.get('lock', None) is None:
        raise ValueError('lock is not set in musicDifficulty')

    id: int = musicDifficulty['musicId']
    difficulty: str = musicDifficulty['musicDifficulty']
    lock: Lock = musicDifficulty['lock']
    score_url: str = musicDifficulty['scoreUrl']
    score_path: str = musicDifficulty['scorePath']
    chart_path: str = musicDifficulty['chartPath']
    jacket: str = musicDifficulty['jacket']

    print(f'Processing music id {id} with difficulty {difficulty}')

    # download score and render chart
    makedirs(score_path.rsplit('/', 1)[0], exist_ok=True)
    print(f'Downloading music id {id} with difficulty {difficulty}')
    download_score(score_url, score_path)

    makedirs(chart_path.rsplit('/', 1)[0], exist_ok=True)
    print(f'Rendering music id {id} with difficulty {difficulty}')
    render_chart(score_path, chart_path, music, jacket, lock)

    print(f'Chart for music id {id} with difficulty {difficulty} saved to {chart_path}')
    

def get_json_url(server: str, json_name: str) -> str:
    if server == 'jp':
        return f'https://sekai-world.github.io/sekai-master-db-diff/{json_name}.json'
    else:
        return f'https://sekai-world.github.io/sekai-master-db-{server}-diff/{json_name}.json'


if __name__ == '__main__':
    import argparse
    # parse arguments
    parser = argparse.ArgumentParser(description='Download and render Sekai music charts.')
    parser.add_argument('--all', '-A', action='store_true', help='Process all charts')
    parser.add_argument('musicId', nargs='*', type=int, help='Process one or more charts by music ID')
    parser.add_argument('-D', '--difficulty', nargs='+', choices=["easy", "normal", "hard", "expert", "master", "append"], help='Specify difficulty for the chart', required=False)
    parser.add_argument('-O', '--output', type=str, default=getcwd(), help='Specify output folder for the charts (default: current directory)')
    parser.add_argument('-S', '--server', choices=["jp", "en", "tc", "kr"], default="jp", help='Specify server for the charts (default: jp)')

    args = parser.parse_args()
    # print(args)

    if not args.all and not args.musicId:
        parser.error('No action requested, add --all or specify a musicId')
    elif args.all and args.musicId:
        parser.error('Conflicting options: --all and musicId')

    musicDifficulties = get_list(get_json_url(args.server, 'musicDifficulties'))
    musics = get_list(get_json_url(args.server, 'musics'))
        
    if not args.all:
        musicDifficulties = [md for md in musicDifficulties if md['musicId'] in args.musicId]
        musics = [music for music in musics if music['id'] in args.musicId]
    if args.difficulty:
        musicDifficulties = [md for md in musicDifficulties if md['musicDifficulty'] in args.difficulty]
    
    lock = Lock()
    # add lock to every musicDifficulty
    for musicDifficulty in musicDifficulties:
        id: int = musicDifficulty['musicId']
        difficulty: str = musicDifficulty['musicDifficulty']
        padId4 = str(id).zfill(4)
        padId3 = str(id).zfill(3)
        
        musicDifficulty['scoreUrl'] = f'https://storage.sekai.best/sekai-{args.server}-assets/music/music_score/{padId4}_01_rip/{difficulty}.txt'
        musicDifficulty['scorePath']= path.join(args.output, 'scores', args.server, padId4, f'{difficulty}.txt')
        musicDifficulty['chartPath'] = path.join(args.output, 'charts', args.server, padId4, f'{difficulty}.svg')
        musicDifficulty['lock'] = lock
        musicDifficulty['jacket'] = f'https://storage.sekai.best/sekai-{args.server}-assets/music/jacket/jacket_s_{padId3}_rip/jacket_s_{padId3}.png'
        

    with ThreadPoolExecutor() as executor:
        executor.map(download_and_render_score, [(music, musicDifficulty) for musicDifficulty in musicDifficulties for music in musics if music['id'] == musicDifficulty['musicId']])
