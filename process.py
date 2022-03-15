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
            img.crop(box).resize((400, 400)).save(thumb_path)
    
    def run_checks(self):
        logger.info(f"{self.url}: Running automatic checks")
        self.issues = []

        tiny_text = self.page.evaluate("""
        () => [...document.querySelectorAll("*")]
            .filter(d => window.getComputedStyle(d)['font-size'].indexOf("px") != -1)
            .filter(d => parseFloat(window.getComputedStyle(d)['font-size']) < 12)
            .map((d) => {
                return {
                    text: d.innerText,
                    size: window.getComputedStyle(d)['font-size']
                }
            })
        """)
        self.page.set_viewport_size({"width": SIZES['mobile'], "height": 700})
        has_sideways_scroll = self.page.evaluate("() => document.body.scrollWidth > window.innerWidth")
        missing_viewport_tag = self.page.evaluate("() => !document.querySelector('meta[name=viewport]')")
        overlapping_elements = []
        for width in SIZES.values():
            self.page.set_viewport_size({"width": width, "height": 700})
            new_overlaps = self.page.evaluate("""
                () => {
                    function overlaps(e1, e2) {
                        const buffer = 5;
                        const rect1 = e1.getBoundingClientRect();
                        const rect2 = e2.getBoundingClientRect();
                        if(rect1.width == 0 || rect2.width == 0) {
                            return false
                        }
                        return !(rect1.right - buffer < rect2.left || 
                            rect1.left + buffer > rect2.right || 
                            rect1.bottom - buffer < rect2.top || 
                            rect1.top + buffer > rect2.bottom)
                    }

                    const elements = [...document.querySelectorAll('.ai2html p')];
                    const overlappingElements = []
                    for(let i = 0; i < elements.length; i++) {
                        const e1 = elements[i];
                        for(let j = i+1; j < elements.length; j++) {
                            const e2 = elements[j];
                            if(overlaps(e1, e2)) {
                                overlappingElements.push({
                                    text1: e1.innerText,
                                    text2: e2.innerText,
                                    width: window.innerWidth
                                })
                            }
                        }
                    }
                    return overlappingElements
                }
            """)
            overlapping_elements.extend(new_overlaps)

        if missing_viewport_tag:
            self.issues.append('* Missing viewport meta tag in `<head>`, needed to tell browser it\'s responsive. Add `<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">`')
        if has_sideways_scroll:
            self.issues.append(f"* Has sideways scrollbars in mobile version – check padding, margins, image widths")

        if tiny_text:
            self.issues.append("* Minimum font size should be 12px, enlarge text in Illustrator")
            for text in tiny_text:
                self.issues.append(f"   * Text `{text['text']}` is too small at {text['size']}")

        if overlapping_elements:
            self.issues.append("* Overlapping elements in ai2html, check [the overflow video](https://www.youtube.com/watch?v=6vHsnjTp3_w) or make a smaller size")
            for overlap in overlapping_elements:
                self.issues.append(f"   * Text `{overlap['text1']}` overlaps with `{overlap['text2']}` at screen width {overlap['width']}")

websites = [w for w in Path("websites.txt").read_text().split("\n") if w != ""]

table_starter = """
|url|mobile|medium|wide|
|---|---|---|---|
"""

readme_md = """"""
issues_md = """"""
toc_md = """"""

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
            readme_md += issues_md
            readme_md += f"\n\n## {site.hostname}\n\n{table_starter}"
            toc_md += f"* [{site.hostname}](#{site.hostname.replace('.','')})\n"
            issues_md = f"\n\n### Automatic Checks\n\n"
            prev_host = site.hostname
        site.load()
        site.screenshot()
        site.run_checks()

        readme_md += site.get_table_row() + "\n"

        issues_md += f"**{site.url}** [Visit ↗]({site.url})\n\n"
        if site.issues:
            issues_md += '\n'.join(site.issues) + '\n\n'
        else:
            issues_md += f"No issues found! 🎉\n\n"

    readme_md += issues_md

    readme_md = (
        "# Data Studio 2022 Responsiveness Test Page\n\n" +
        "Quick checks to make sure your pages are looking their best.\n\n" +
        toc_md +
        "\n\n" +
        readme_md
    )

    Path("README.md").write_text(readme_md)

    browser.close()
