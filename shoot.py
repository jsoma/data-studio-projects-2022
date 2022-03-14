from pathlib import Path
import logging
from urllib.parse import urlparse
from PIL import Image
import time

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OUTPUT_DIR = "screenshots"
SIZES = {"mobile": 400, "medium": 900, "wide": 1300}


class Website:
    def __init__(self, page, url):
        self.page = page
        self.url = url

        pieces = urlparse(url)
        self.hostname = pieces.hostname
        if pieces.path.endswith("html"):
            self.urlpath = pieces.path.strip("/")
        else:
            self.urlpath = pieces.path.strip("/") + "/index.html"
        self.urlpath = self.urlpath.strip("/")

    def load(self):
        """Load the web page"""
        logger.info(f"{self.url}: Loading")
        self.page.goto(self.url)
        time.sleep(1)
        self.page.evaluate(
            "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });"
        )
        time.sleep(2)

    def screenshot(self):
        """Take a screenshot at each screen size"""
        self.load()
        for size in SIZES.keys():
            self.screenshot_one(size)

    def get_table_row(self):
        """Markdown display of screenshots for this web page"""
        title = self.page.title() or self.urlpath
        desc = f"|[{title}]({self.url})|"
        images = [
            f"[![{size}]({self.shot_path(size, 'thumb')})]({self.shot_path(size)})"
            for size in SIZES.keys()
        ]
        return desc + "|".join(images) + "|"

    def shot_path(self, size, version="full"):
        """Returns the file path for a given screenshot size and version"""
        basename = self.urlpath.replace("/", "_")
        filename = f"{basename}-{size}-{version}.jpg"
        return Path(OUTPUT_DIR).joinpath(self.hostname).joinpath(filename)

    def screenshot_one(self, size):
        """Create a screenshot at a given screen width"""
        width = SIZES[size]
        filepath = self.shot_path(size)
        self.page.set_viewport_size({"width": width, "height": 700})
        time.sleep(0.5)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"{self.url}: {width}px screenshot to {filepath}")

        self.page.screenshot(path=filepath, full_page=True, type='jpeg')

        thumb_path = self.shot_path(size, "thumb")
        logger.info(f"{self.url}: Creating thumbnail at {thumb_path}")
        with Image.open(filepath) as img:
            box = (0, 0, img.size[0], img.size[0])
            img.crop(box).resize((600, 600)).save(thumb_path)


websites = [w for w in Path("websites.txt").read_text().split("\n") if w != ""]

table_starter = """
|url|mobile|medium|wide|
|---|---|---|---|
"""

readme = """
# Data Studio 2022 Responsiveness Test Page

"""

with sync_playwright() as p:
    browser = p.chromium.launch(
        args=[
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
    )
    page = browser.new_page()

    prev_host = None
    for website in websites:
        site = Website(page, website)
        if site.hostname != prev_host:
            readme += f"\n\n## {site.hostname}\n\n{table_starter}"
            prev_host = site.hostname
        site.screenshot()
        readme += site.get_table_row() + "\n"

    Path("README.md").write_text(readme)

    browser.close()
