import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import openai

logger = logging.getLogger(__name__)


# 1. Жесткие схемы контракта извлечения фактов (защита от галлюцинаций)
class InsuranceFact(BaseModel):
    parameter_code: str = Field(
        description="Уникальный код параметра из карточки (например, 'deductible', 'franchise_amount', 'risks')"
    )
    value: Optional[str] = Field(
        description="Найденное значение. Если в документе данных нет, строго передавать null, ничего не выдумывая."
    )
    quote: Optional[str] = Field(
        description="Точная цитата из текста документа, подтверждающая значение. Обязательна, если value не null."
    )
    page_or_section: Optional[str] = Field(
        description="Номер страницы, раздела или пункта документа, где найдено значение."
    )
    confidence: float = Field(
        description="Уверенность модели в извлечении от 0.0 до 1.0. Если значение предположительное или неточное, указывать низкую уверенность."
    )


class DocumentExtractionResult(BaseModel):
    document_id: str = Field(description="Идентификатор или имя обрабатываемого документа")
    facts: List[InsuranceFact] = Field(description="Список извлеченных фактов по параметрам")


def extract_document_facts(document_text: str, document_id: str, parameters_schema: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Строгое извлечение фактов из текста документа с привязкой к цитатам и защитой от галлюцинаций.
    Использует Structured Outputs через Pydantic.
    """
    system_prompt = (
        "Ты строгий аудитор страховой документации. Твоя задача — извлечь параметры из текста документа.\n"
        "ПРАВИЛА:\n"
        "1. Запрещено додумывать, экстраполировать или дописывать данные от себя.\n"
        "2. Если параметр не упомянут явно в тексте документа, поле 'value' должно быть строго null, а 'quote' пустым.\n"
        "3. Для каждого найденного параметра ты ОБЯЗАН привести точную цитату из текста документа в поле 'quote'.\n"
        "4. Всегда возвращай результат строго в формате JSON, соответствующем заданной схеме."
    )

    user_content = (
        f"Документ ID: {document_id}\n\n"
        f"Список целевых параметров для поиска:\n{json.dumps(parameters_schema, ensure_ascii=False, indent=2)}\n\n"
        f"Текст документа для анализа:\n---\n{document_text}\n---\n"
    )

    try:
        client = openai.OpenAI()
        
        # Используем современный интерфейс beta.chat.completions.parse для гарантированного соответствия Pydantic схеме
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",  # Или модель, которая используется у вас в проекте
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format=DocumentExtractionResult,
            temperature=0.0  # Нулевая температура для максимальной точности и минимальных галлюцинаций
        )

        result = completion.choices.message.parsed
        return result.model_dump()

    except Exception as e:
        logger.error(f"Ошибка при строгом извлечении фактов для документа {document_id}: {e}")
        # Возвращаем пустую безопасную структуру в случае сбоя
        return {
            "document_id": document_id,
            "facts": []
        }
