"""
Веб-приложение Flask для системы генерации лидов 2GIS
"""
import os
import socket
import logging
import threading
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS

from src.scraper import TwoGISScraper
from src.excel_exporter import ExcelExporter
from src.config import CITIES_BY_COUNTRY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


@app.errorhandler(500)
@app.errorhandler(404)
@app.errorhandler(405)
def api_json_error(e):
    """Возврат JSON вместо HTML при ошибках API"""
    if request.path.startswith('/api/'):
        code = getattr(e, 'code', 500)
        msg = getattr(e, 'description', 'Ошибка сервера') if hasattr(e, 'description') else 'Ошибка сервера'
        return jsonify({'error': str(msg)}), code
    return Response('<h1>Ошибка</h1>', status=getattr(e, 'code', 500), mimetype='text/html')


# Глобальные переменные для хранения состояния поиска
search_status = {
    'is_running': False,
    'progress': 0,
    'total': 0,
    'current': '',
    'results': [],
    'error': None
}

# Блокировка для потокобезопасности
status_lock = threading.Lock()


def update_status(progress=0, total=0, current='', results=None, error=None, is_running=False):
    """Обновление статуса поиска"""
    with status_lock:
        search_status['progress'] = progress
        search_status['total'] = total
        search_status['current'] = current
        search_status['is_running'] = is_running
        search_status['error'] = error
        if results is not None:
            search_status['results'] = results


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html', cities_by_country=CITIES_BY_COUNTRY)


@app.route('/api/search', methods=['POST'])
def search_companies():
    """API endpoint для поиска компаний"""
    global search_status

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({'error': 'Неверный формат запроса'}), 400

    country = (data.get('country') or '').strip() or 'Россия'
    city = (data.get('city') or '').strip()
    category = (data.get('category') or '').strip()
    max_results = data.get('max_results')
    whole_country = data.get('whole_country', False)

    if not whole_country and not city:
        return jsonify({'error': 'Выберите город или "Вся страна"'}), 400

    with status_lock:
        if search_status['is_running']:
            return jsonify({'error': 'Поиск уже выполняется'}), 400
        search_status['is_running'] = True
        search_status['progress'] = 0
        search_status['total'] = 0
        search_status['current'] = ''
        search_status['results'] = []
        search_status['error'] = None

    thread = threading.Thread(
        target=run_search,
        args=(country, city, category, max_results, whole_country)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Поиск запущен', 'status': 'started'})


def run_search(country, city, category, max_results, whole_country=False):
    """Выполнение поиска в отдельном потоке"""
    global search_status

    def progress_callback(current, total, message):
        update_status(progress=current, total=total, current=message, is_running=True)

    try:
        update_status(is_running=True, current='Инициализация поиска...', progress=0, total=0)

        with TwoGISScraper(headless=True) as scraper:
            all_companies = []
            seen_urls = set()

            if whole_country:
                cities = CITIES_BY_COUNTRY.get(country, [])
                if not cities:
                    update_status(is_running=False, error=f'Нет городов для страны: {country}')
                    return
                total_cities = len(cities)
                for idx, c in enumerate(cities, 1):
                    if max_results and len(all_companies) >= max_results:
                        break
                    city_max = (max_results - len(all_companies)) if max_results else None
                    update_status(
                        progress=len(all_companies),
                        total=max_results or 0,
                        current=f'Город {idx}/{total_cities}: {c}',
                        is_running=True
                    )
                    companies = scraper.search_companies(
                        city=c,
                        category=category if category else None,
                        max_results=city_max,
                        progress_callback=progress_callback,
                        country=country
                    )
                    for comp in companies:
                        if comp.url and comp.url not in seen_urls:
                            seen_urls.add(comp.url)
                            all_companies.append(comp)
                companies = all_companies
            else:
                companies = scraper.search_companies(
                    city=city,
                    category=category if category else None,
                    max_results=max_results,
                    progress_callback=progress_callback,
                    country=country
                )
                for comp in companies:
                    comp.city = city

            if not companies:
                update_status(
                    is_running=False,
                    error='Компании не найдены. Проверьте параметры поиска.'
                )
                return

            results = [c.to_dict() for c in companies]
            update_status(
                progress=len(results),
                total=len(results),
                current=f'Завершено! Найдено {len(results)} компаний',
                results=results,
                is_running=False
            )
            logger.info(f"Найдено компаний: {len(results)}")

    except Exception as e:
        logger.error(f"Ошибка при поиске: {str(e)}", exc_info=True)
        update_status(is_running=False, error=f'Ошибка: {str(e)}')


@app.route('/api/status', methods=['GET'])
def get_status():
    """Получение статуса поиска"""
    with status_lock:
        return jsonify(search_status.copy())


@app.route('/api/download', methods=['POST'])
def download_excel():
    """Скачивание результатов в Excel"""
    global search_status
    
    with status_lock:
        results = search_status.get('results', [])
    
    if not results:
        return jsonify({'error': 'Нет результатов для экспорта'}), 400
    
    try:
        # Создание объектов Company из словарей
        from src.models import Company
        companies = []
        for result in results:
            company = Company(
                name=result.get('Название компании', ''),
                phone=result.get('Телефон', '') if result.get('Телефон') != 'N/A' else None,
                address=result.get('Адрес', '') if result.get('Адрес') != 'N/A' else None,
                rating=result.get('Рейтинг') if result.get('Рейтинг') != 'N/A' else None,
                voters_count=result.get('Количество голосов') if result.get('Количество голосов') != 'N/A' else None,
                info=result.get('Информация о компании', '') if result.get('Информация о компании') != 'N/A' else None,
                url=result.get('Ссылка', '') if result.get('Ссылка') != 'N/A' else None,
                city=result.get('Город', '') if result.get('Город') != 'N/A' else None
            )
            companies.append(company)
        
        # Экспорт в Excel
        exporter = ExcelExporter()
        filename = '2gis_results.xlsx'
        filepath = exporter.export_to_excel(companies, filename)
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при экспорте: {str(e)}", exc_info=True)
        return jsonify({'error': f'Ошибка экспорта: {str(e)}'}), 500


@app.route('/api/reset', methods=['POST'])
def reset_status():
    """Сброс статуса поиска"""
    global search_status
    with status_lock:
        search_status = {
            'is_running': False,
            'progress': 0,
            'total': 0,
            'current': '',
            'results': [],
            'error': None
        }
    return jsonify({'message': 'Статус сброшен'})


def _find_free_port(start: int = 5000, end: int = 5020) -> int:
    """Найти свободный порт в диапазоне start..end. При занятости всех портов — OSError."""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise OSError(f"Все порты в диапазоне {start}-{end - 1} заняты")


if __name__ == '__main__':
    import webbrowser
    import time

    port = int(os.environ.get('FLASK_PORT', 0)) or _find_free_port()
    url = f'http://localhost:{port}'

    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)

    def open_browser():
        time.sleep(2)
        webbrowser.open(url)

    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Thread(target=open_browser, daemon=True).start()

    print("\n" + "="*60)
    print("2GIS Lead Generation System - Веб-интерфейс")
    print("="*60)
    print(f"\nПриложение: {url}")
    print("Браузер откроется автоматически. Для остановки: Ctrl+C\n")
    print("="*60 + "\n")

    app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False)
