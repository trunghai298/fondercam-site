import re, subprocess, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

CONTACT = "support@fondercam.online"
# The pages that give Fonder's contact address: each names it in its text and its footer.
CONTACT_PAGES = ["support/index.html", "vi/support/index.html", "privacy/index.html", "terms/index.html"]


def tracked_pages():
    out = subprocess.run(["git", "ls-files", "*.html"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.split()]


class ContactAddressTests(unittest.TestCase):
    def test_no_page_gives_a_personal_gmail_address(self):
        found = [p.relative_to(ROOT).as_posix() for p in tracked_pages()
                 if re.search(r"[\w.+-]+@gmail\.com", p.read_text(encoding="utf-8"))]
        self.assertEqual(found, [])

    def test_each_contact_page_links_the_support_address_twice(self):
        for page in CONTACT_PAGES:
            text = (ROOT / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertEqual(text.count(f'href="mailto:{CONTACT}">{CONTACT}</a>'), 2)


if __name__ == "__main__":
    unittest.main()
