"""
Модели данных для системы генерации лидов
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Company:
    """Модель компании с данными из 2GIS"""
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    voters_count: Optional[int] = None
    info: Optional[str] = None
    url: Optional[str] = None
    city: Optional[str] = None

    def to_dict(self) -> dict:
        """Преобразование в словарь для экспорта"""
        return {
            'Название компании': self.name,
            'Телефон': self.phone or 'N/A',
            'Адрес': self.address or 'N/A',
            'Рейтинг': self.rating or 'N/A',
            'Количество голосов': self.voters_count or 'N/A',
            'Информация о компании': self.info or 'N/A',
            'Ссылка': self.url or 'N/A',
            'Город': self.city or 'N/A'
        }
