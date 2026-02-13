"""
CLI интерфейс для системы генерации лидов 2GIS
"""
import logging
import sys
from typing import Optional

import click

from .scraper import TwoGISScraper
from .excel_exporter import ExcelExporter

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Система генерации лидов из данных 2GIS"""
    pass


@cli.command()
@click.option('--city', '-c', required=True, help='Название города (например: Москва)')
@click.option('--country', default='Россия', help='Страна: Россия, Казахстан, Узбекистан')
@click.option('--category', '-cat', help='Категория бизнеса (например: Кафе, Рестораны)')
@click.option('--output', '-o', default='2gis_results.xlsx', help='Имя выходного Excel файла')
@click.option('--max-results', '-m', type=int, help='Максимальное количество результатов')
@click.option('--headless/--no-headless', default=True, help='Запуск браузера в headless режиме')
def search(city: str, country: str, category: Optional[str], output: str, max_results: Optional[int], headless: bool):
    """
    Поиск компаний в 2GIS и экспорт результатов в Excel
    
    Примеры использования:
    
    \b
    Поиск кафе в Москве:
    python main.py search --city Москва --category Кафе
    
    \b
    Поиск ресторанов в Санкт-Петербурге с ограничением в 50 результатов:
    python main.py search -c "Санкт-Петербург" -cat Рестораны -m 50
    
    \b
    Поиск всех компаний в Екатеринбурге:
    python main.py search --city Екатеринбург
    """
    click.echo(f"🔍 Начинаю поиск компаний...")
    click.echo(f"   Страна: {country}")
    click.echo(f"   Город: {city}")
    if category:
        click.echo(f"   Категория: {category}")
    click.echo(f"   Максимум результатов: {max_results or 'без ограничений'}")
    click.echo()
    
    companies = []
    
    try:
        # Инициализация скрапера
        with TwoGISScraper(headless=headless) as scraper:
            # Поиск компаний
            click.echo("⏳ Загрузка данных с сайта 2GIS...")
            companies = scraper.search_companies(
                city=city,
                category=category,
                max_results=max_results,
                country=country
            )
        
        if not companies:
            click.echo("❌ Компании не найдены. Проверьте параметры поиска.")
            return
        
        # Экспорт в Excel
        click.echo(f"\n📊 Найдено компаний: {len(companies)}")
        click.echo(f"💾 Экспорт в Excel...")
        
        exporter = ExcelExporter()
        filepath = exporter.export_to_excel(companies, output)
        
        click.echo(f"\n✅ Готово! Результаты сохранены в: {filepath}")
        click.echo(f"\n📋 Данные включают:")
        click.echo(f"   - Название компании")
        click.echo(f"   - Телефон")
        click.echo(f"   - Адрес")
        click.echo(f"   - Рейтинг")
        click.echo(f"   - Количество голосов")
        click.echo(f"   - Информация о компании")
        click.echo(f"   - Ссылка на страницу")
        
    except KeyboardInterrupt:
        click.echo("\n\n⚠️  Операция прервана пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Ошибка при выполнении поиска: {str(e)}", exc_info=True)
        click.echo(f"\n❌ Произошла ошибка: {str(e)}")
        click.echo("Проверьте логи для подробной информации.")
        sys.exit(1)


if __name__ == '__main__':
    cli()
