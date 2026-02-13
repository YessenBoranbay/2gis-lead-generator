"""
Веб-скрапер для извлечения данных о компаниях с сайта 2GIS.
Использует пагинацию и парсинг из списка результатов (без посещения страниц компаний).
"""
import time
import re
import logging
from typing import List, Optional
from urllib.parse import quote, urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager

from .models import Company

logger = logging.getLogger(__name__)


class TwoGISScraper:
    """Скрапер 2GIS: пагинация + парсинг из списка результатов"""

    COUNTRY_DOMAINS = {
        'Россия': 'https://2gis.ru',
        'Казахстан': 'https://2gis.kz',
        'Узбекистан': 'https://2gis.uz',
    }
    BASE_URL = "https://2gis.ru"
    PAGE_DELAY = 2

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self._setup_driver()

    def _setup_driver(self):
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(10)

    def _normalize_city(self, city: str) -> str:
        city_mapping = {
            'москва': 'moscow', 'санкт-петербург': 'spb', 'спб': 'spb',
            'екатеринбург': 'ekb', 'новосибирск': 'novosibirsk', 'казань': 'kazan',
            'нижний новгород': 'nizhniy_novgorod', 'челябинск': 'chelyabinsk',
            'самара': 'samara', 'омск': 'omsk', 'ростов-на-дону': 'rostov_na_donu',
            'уфа': 'ufa', 'красноярск': 'krasnoyarsk', 'воронеж': 'voronezh',
            'пермь': 'perm', 'волгоград': 'volgograd', 'краснодар': 'krasnodar',
            'алматы': 'almaty', 'астана': 'astana', 'нур-султан': 'astana',
            'шымкент': 'shymkent', 'ташкент': 'tashkent', 'самарканд': 'samarkand',
            'усть-каменогорск': 'ust_kamenogorsk', 'петропавловск': 'petropavl',
            'кокшетау': 'kokchetav', 'талдыкорган': 'taldykorgan', 'атырау': 'atyrau',
        }
        city_lower = city.lower().strip()
        if city_lower in city_mapping:
            return city_mapping[city_lower]
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
        }
        return ''.join(translit_map.get(c, c) if c.isalpha() else ('_' if c in ' -' else c) for c in city_lower)

    def _build_search_url(self, city: str, category: Optional[str] = None, country: Optional[str] = None, page: int = 1) -> str:
        base = self.COUNTRY_DOMAINS.get(country or 'Россия', self.BASE_URL)
        city_norm = self._normalize_city(city)
        if category:
            cat_enc = quote(category.lower())
            path = f"/{city_norm}/search/{cat_enc}"
        else:
            path = f"/{city_norm}/search"
        if page > 1:
            path += f"/page/{page}"
        return base + path

    def _find_phone_card(self, link) -> Optional[object]:
        """Найти наименьший контейнер с одной фирмой (избежать телефонов из соседних карточек)"""
        p = link.find_parent()
        while p:
            firm_links = p.find_all('a', href=re.compile(r'/firm/\d+'))
            if len(firm_links) == 1:
                return p
            p = p.find_parent()
        return None

    def _extract_phones_from_card(self, card) -> Optional[str]:
        """Извлечение телефонов из tel: ссылок в карточке"""
        if not card:
            return None
        phones = []
        seen = set()
        for tel in card.find_all('a', href=re.compile(r'^tel:')):
            ph = tel.get('href', '').replace('tel:', '').strip()
            if ph and len(ph) >= 10:
                key = re.sub(r'\D', '', ph)[-10:]
                if key not in seen:
                    seen.add(key)
                    phones.append(ph)
        return "; ".join(phones) if phones else None

    def _fetch_phone_from_firm_page(self, firm_url: str) -> Optional[str]:
        """Загрузка страницы фирмы и извлечение телефона"""
        try:
            self.driver.get(firm_url.split('?')[0])
            WebDriverWait(self.driver, 15).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            time.sleep(2)
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'lxml')
            phones = []
            seen = set()
            for tel in soup.find_all('a', href=re.compile(r'tel:', re.I)):
                ph = re.sub(r'^tel:', '', tel.get('href', ''), flags=re.I).strip()
                if ph and len(re.sub(r'\D', '', ph)) >= 10:
                    key = re.sub(r'\D', '', ph)[-10:]
                    if key not in seen:
                        seen.add(key)
                        phones.append(ph)
            if not phones:
                for m in re.finditer(r'tel:([0-9+\-\(\)\s]+)', html, re.I):
                    ph = re.sub(r'\s+', '', m.group(1).strip())
                    if len(ph) >= 10:
                        key = re.sub(r'\D', '', ph)[-10:]
                        if key not in seen:
                            seen.add(key)
                            phones.append(ph)
            return "; ".join(phones) if phones else None
        except Exception as e:
            logger.debug(f"Ошибка загрузки телефона с {firm_url}: {e}")
            return None

    def _parse_search_page(self, html: str, base_url: str) -> List[Company]:
        """Парсинг карточек компаний со страницы поиска (без перехода на страницу фирмы)."""
        soup = BeautifulSoup(html, 'lxml')
        companies = []
        seen_ids = set()

        firm_links = soup.find_all('a', href=re.compile(r'/firm/\d+'))
        for link in firm_links:
            href = link.get('href', '')
            if '/branches/' in href:
                continue
            full_url = urljoin(base_url, href) if href.startswith('/') else href
            firm_id = re.search(r'/firm/(\d+)', href)
            if firm_id and firm_id.group(1) in seen_ids:
                continue
            if firm_id:
                seen_ids.add(firm_id.group(1))

            name = (link.get_text(strip=True) or '').strip()
            if not name or len(name) < 2:
                continue

            card = link.find_parent(['article', 'div', 'section', 'li'], recursive=True)
            if not card:
                card = link
            for _ in range(10):
                p = card.find_parent()
                if not p:
                    break
                txt = p.get_text(separator=' ', strip=True)
                if 100 < len(txt) < 5000 and re.search(r'\d+[.,]\d+', txt) and re.search(r'оценок', txt, re.I):
                    card = p
                    break
                card = p
            card_text = card.get_text(separator=' ', strip=True) if card else ''

            phone_card = self._find_phone_card(link)
            phone = self._extract_phones_from_card(phone_card) if phone_card else None

            rating = None
            rating_el = card.find(string=re.compile(r'^\d+\.\d+$'))
            if rating_el:
                try:
                    rating = float(rating_el.strip())
                except ValueError:
                    pass
            if rating is None:
                m = re.search(r'(\d+[.,]\d+)', card_text)
                if m:
                    try:
                        rating = float(m.group(1).replace(',', '.'))
                    except ValueError:
                        pass

            voters_count = None
            voters_el = card.find(string=re.compile(r'\d+\s*оценок?', re.I))
            if voters_el:
                m = re.search(r'(\d+)', voters_el)
                if m:
                    voters_count = int(m.group(1))
            if voters_count is None:
                m = re.search(r'(\d+)\s*оценок', card_text, re.I)
                if m:
                    voters_count = int(m.group(1))

            address = None
            for addr_sel in ['[data-testid="address"]', '.address', '[class*="address"]', '[class*="Address"]', 'a[href^="geo:"]']:
                el = card.select_one(addr_sel)
                if el:
                    address = el.get_text(strip=True)
                    break
            if not address:
                addr_re = re.compile(r'(улица|ул\.|пр\.|бульвар|переулок|площадь|проспект|шоссе|м\.|метро|д\.|дом|корп\.|стр\.)', re.I)
                for el in card.find_all(['span', 'div', 'p', 'a']):
                    t = el.get_text(strip=True)
                    if 10 < len(t) < 200 and addr_re.search(t):
                        if not re.search(r'(услуги|работаем|предлагаем|компания|салон|магазин)', t, re.I):
                            address = t
                            break
            if not address:
                m_addr = re.search(
                    r'([^,]{10,150}(?:улица|ул\.|пр\.|бульвар|переулок|площадь|проспект|шоссе)[^,]{0,80})',
                    card_text, re.I
                )
                if m_addr:
                    address = m_addr.group(1).strip()[:250]

            info = None
            desc_exclude = re.compile(r'(улица|ул\.|пр\.|бульвар|переулок|площадь|проспект|шоссе|м\.\s|метро\s|д\.\s|дом\s|корп\.|стр\.)', re.I)
            for desc_sel in ['[data-testid="description"]', '.description', '[class*="description"]', '[class*="snippet"]', '[class*="Snippet"]']:
                el = card.select_one(desc_sel)
                if el:
                    txt = el.get_text(strip=True)
                    if 20 < len(txt) < 800 and txt != name and not re.match(r'^\d+[.,]\d+', txt):
                        if not desc_exclude.search(txt):
                            info = txt[:500]
                            break
            if not info:
                for el in card.find_all(['span', 'div', 'p']):
                    t = el.get_text(strip=True)
                    if 30 < len(t) < 600 and t != name and t != address:
                        if not re.match(r'^\d+', t) and 'оценок' not in t and not desc_exclude.search(t):
                            info = t[:500]
                            break

            companies.append(Company(
                name=name,
                phone=phone,
                address=address,
                rating=rating,
                voters_count=voters_count,
                info=info,
                url=full_url
            ))

        return companies

    def search_companies(self, city: str, category: Optional[str] = None,
                         max_results: Optional[int] = None,
                         progress_callback=None,
                         country: Optional[str] = None) -> List[Company]:
        base_url = self.COUNTRY_DOMAINS.get(country or 'Россия', self.BASE_URL)
        all_companies = []
        page = 1
        max_pages = 200

        try:
            while page <= max_pages:
                url = self._build_search_url(city, category, country, page)
                if progress_callback:
                    progress_callback(len(all_companies), 0, f'Загрузка страницы {page}...')

                self.driver.get(url)
                WebDriverWait(self.driver, 20).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                time.sleep(3)

                html = self.driver.page_source
                companies = self._parse_search_page(html, base_url)

                if not companies:
                    break

                for c in companies:
                    if c.url and not any(x.url == c.url for x in all_companies):
                        if not c.phone and c.url:
                            if progress_callback:
                                progress_callback(len(all_companies), max_results or 0, f'Загрузка телефона: {c.name[:40]}...')
                            c.phone = self._fetch_phone_from_firm_page(c.url)
                            time.sleep(1)
                        c.city = city
                        all_companies.append(c)
                        if max_results and len(all_companies) >= max_results:
                            break

                if max_results and len(all_companies) >= max_results:
                    all_companies = all_companies[:max_results]
                    break

                has_next = bool(self.driver.find_elements(By.CSS_SELECTOR, f'a[href*="/page/{page + 1}"]'))
                if not has_next:
                    break

                page += 1
                time.sleep(self.PAGE_DELAY)

            if progress_callback:
                progress_callback(len(all_companies), len(all_companies), f'Найдено {len(all_companies)} компаний')
            logger.info(f"Найдено компаний: {len(all_companies)}")
            return all_companies

        except Exception as e:
            logger.error(f"Ошибка поиска: {e}", exc_info=True)
            if progress_callback:
                progress_callback(0, 0, str(e))
            return all_companies

    def close(self):
        if self.driver:
            self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
