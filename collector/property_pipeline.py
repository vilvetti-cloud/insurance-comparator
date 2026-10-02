import logging
import json
from typing import Dict, Any, List

from collector.llm import extract_document_facts
from database.repositories.document import DocumentRepository
from database.repositories.evidence import EvidenceRepository
from database.repositories.field import FieldRepository

logger = logging.getLogger(__name__)


class PropertyPipeline:
    """
    Контролируемый пайплайн обработки документов по страхованию имущества:
    Документ -> Строгое извлечение фактов с цитатами -> Валидация -> Запись в БД.
    """

    def __init__(self):
        self.document_repo = DocumentRepository()
        self.evidence_repo = EvidenceRepository()
        self.field_repo = FieldRepository()

    def run_pipeline(self, document_id: str, document_text: str, parameters_schema: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Запускает полный цикл обработки имущественного документа:
        1. Проверка текста документа.
        2. Извлечение фактов с жестким контрактом (без галлюцинаций).
        3. Валидация наличия цитат и фильтрация пустых значений.
        4. Сохранение подтвержденных фактов и доказательств в базу данных.
        """
        logger.info(f"Запуск имущественного пайплайна обработки для документа ID: {document_id}")

        if not document_text or not document_text.strip():
            logger.warning(f"Документ имущества {document_id} пуст. Обработка невозможна.")
            return {"status": "error", "message": "Document text is empty"}

        # Шаг 1: Извлечение фактов с помощью LLM (схема Pydantic + нулевая температура)
        extraction_result = extract_document_facts(
            document_text=document_text,
            document_id=document_id,
            parameters_schema=parameters_schema
        )

        facts = extraction_result.get("facts", [])
        logger.info(f"Извлечено сырых фактов по имуществу для документа {document_id}: {len(facts)}")

        saved_facts_count = 0

        # Шаг 2 & 3: Валидация и сохранение фактов с подтверждающими цитатами
        for fact in facts:
            param_code = fact.get("parameter_code")
            value = fact.get("value")
            quote = fact.get("quote")
            confidence = fact.get("confidence", 0.0)
            page_section = fact.get("page_or_section")

            # Жесткое правило: если value отсутствует или null — игнорируем
            if value is None or str(value).strip().lower() in ["null", "none", ""]:
                logger.debug(f"Параметр имущества {param_code} пропущен: значение не найдено в документе.")
                continue

            # Жесткое правило: если найдено значение, но нет цитаты — считаем это галлюцинацией и отбраковываем
            if not quote or not quote.strip():
                logger.warning(
                    f"Отброшен факт имущества для параметра '{param_code}': значение найдено ('{value}'), "
                    f"но отсутствует обязательная подтверждающая цитата из документа."
                )
                continue

            # Дополнительная проверка уверенности модели
            if confidence < 0.5:
                logger.warning(
                    f"Низкая уверенность ({confidence}) для параметра имущества '{param_code}' со значением '{value}'. "
                    f"Требует ручной проверки."
                )

            try:
                # Шаг 4: Сохранение подтвержденного факта и доказательства (evidence) в репозитории базы данных
                self.field_repo.save_extracted_value(
                    document_id=document_id,
                    parameter_code=param_code,
                    value=value,
                    confidence=confidence
                )

                self.evidence_repo.save_evidence(
                    document_id=document_id,
                    parameter_code=param_code,
                    quote=quote,
                    page_or_section=page_section,
                    confidence=confidence
                )

                saved_facts_count += 1

            except Exception as db_err:
                logger.error(f"Ошибка сохранения факта имущества '{param_code}' в базу данных: {db_err}")

        logger.info(
            f"Имущественный пайплайн для документа {document_id} завершен. "
            f"Сохранено подтвержденных фактов с цитатами: {saved_facts_count} из {len(facts)}"
        )

        return {
            "status": "success",
            "document_id": document_id,
            "total_extracted": len(facts),
            "saved_verified_facts": saved_facts_count
        }
