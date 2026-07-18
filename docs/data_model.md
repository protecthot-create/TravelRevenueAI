# Data Model — Travel Revenue AI MVP

## Проект
Travel Revenue AI

## Назначение документа
Этот документ описывает основные сущности системы Travel Revenue AI на уровне модели данных MVP.

Документ опирается на:
- `docs/vision.md`
- `docs/system_architecture.md`
- `docs/revenue_scoring_engine_spec.md`
- `docs/decision_card_spec.md`
- `docs/implementation_plan.md`

Код в этом документе не приводится.

---

## 1. Agency

### Назначение
Турагентство, которое использует систему. Основной контекст для всех сигналов, оценок и рекомендаций.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| agency_id | UUID | Да | Уникальный идентификатор |
| name | string | Да | Название агентства |
| size | enum | Да | Размер: small / medium |
| specialization | string | Нет | Специализация агентства |
| timezone | string | Да | Часовой пояс |
| created_at | datetime | Да | Дата создания |
| updated_at | datetime | Да | Дата обновления |

### Связи
- имеет много `User`
- имеет много `Signal`
- имеет много `Decision Card`
- имеет много `Morning Brief`
- имеет много `Data Source`

---

## 2. User

### Назначение
Пользователь системы — сотрудник или владелец турагентства.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| user_id | UUID | Да | Уникальный идентификатор |
| agency_id | UUID | Да | Ссылка на агентство |
| email | string | Да | Email пользователя |
| role | enum | Да | Роль: owner / manager / viewer |
| preferences | JSON | Нет | Пользовательские настройки |
| created_at | datetime | Да | Дата создания |
| updated_at | datetime | Да | Дата обновления |

### Связи
- принадлежит к `Agency`
- оставляет много `Feedback`
- выполняет много `Action`

---

## 3. Signal

### Назначение
Исходный сигнал из внешнего или внутреннего источника. Сырые данные до нормализации и оценки.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| signal_id | UUID | Да | Уникальный идентификатор |
| agency_id | UUID | Да | Ссылка на агентство |
| source_id | UUID | Да | Ссылка на источник данных |
| signal_type | enum | Да | Тип: opportunity / risk / market / operational |
| raw_data | JSON | Да | Сырые данные сигнала |
| status | enum | Да | Статус: new / normalized / scored / filtered / rejected |
| created_at | datetime | Да | Дата поступления |
| updated_at | datetime | Да | Дата обновления |

### Связи
- принадлежит к `Agency`
- поступает из `Data Source`
- порождает один `Decision Card`
- имеет один `Action`

---

## 4. Decision Card

### Назначение
Основной продуктовый объект. Объединяет оценку сигнала, денежный эффект и рекомендацию для пользователя.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| decision_card_id | UUID | Да | Уникальный идентификатор |
| signal_id | UUID | Да | Ссылка на исходный сигнал |
| agency_id | UUID | Да | Ссылка на агентство |
| card_type | enum | Да | Тип: Opportunity / Risk / Market Insight / Operational Insight |
| title | string | Да | Заголовок карточки |
| summary | string | Да | Краткое описание |
| money_effect_display | string | Да | Денежный эффект для отображения |
| importance_label | enum | Да | Уровень важности |
| why_it_matters | text | Да | Объяснение важности |
| what_to_do | text | Да | Рекомендуемое действие |
| deadline_display | string | Да | Дедлайн для отображения |
| confidence_display | string | Да | Уверенность для отображения |
| source_display | string | Да | Источник для отображения |
| status_display | enum | Нет | Статус: active / done / dismissed |
| score | decimal | Да | Внутренний score |
| priority_label | enum | Да | Внутренняя метка приоритета |
| filter_result | enum | Да | Результат фильтрации: pass / reject / needs_review |
| breakdown | JSON | Нет | Разбивка оценки |
| reasoning_trace | text | Нет | Трассировка решения |
| applicable_modifiers | JSON | Нет | Применённые модификаторы |
| generated_at | datetime | Да | Дата генерации |
| updated_at | datetime | Да | Дата обновления |

### Связи
- порождена от `Signal`
- принадлежит к `Agency`
- входит в `Morning Brief`
- имеет много `Feedback`
- имеет один `Action`

---

## 5. Morning Brief

### Назначение
Ежедневный брифинг, собранный из приоритетных Decision Card.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| brief_id | UUID | Да | Уникальный идентификатор |
| agency_id | UUID | Да | Ссылка на агентство |
| date | date | Да | Дата брифа |
| top_opportunities | JSON | Да | Список top-5 Decision Card |
| top_risks | JSON | Да | Список top-3 Decision Card |
| main_action_id | UUID | Нет | Ссылка на главное действие дня |
| summary_text | text | Да | Краткий текст брифа |
| status | enum | Да | Статус: draft / sent / read |
| created_at | datetime | Да | Дата создания |
| sent_at | datetime | Нет | Дата отправки |

### Связи
- принадлежит к `Agency`
- содержит много `Decision Card`
- указывает на одно `Decision Card` как главное действие

---

## 6. Action

### Назначение
Конкретное действие, которое рекомендуется выполнить на основе Decision Card.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| action_id | UUID | Да | Уникальный идентификатор |
| decision_card_id | UUID | Да | Ссылка на Decision Card |
| signal_id | UUID | Да | Ссылка на исходный сигнал |
| user_id | UUID | Нет | Ссылка на исполнителя |
| description | text | Да | Описание действия |
| deadline | datetime | Да | Дедлайн |
| status | enum | Да | Статус: pending / in_progress / done / cancelled |
| time_estimate | integer | Нет | Оценка времени в минутах |
| created_at | datetime | Да | Дата создания |
| updated_at | datetime | Да | Дата обновления |

### Связи
- порождено от `Decision Card`
- связано с `Signal`
- может быть назначено на `User`
- имеет много `Feedback`

---

## 7. Feedback

### Назначение
Обратная связь пользователя по Decision Card или Action. Используется для калибровки системы.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| feedback_id | UUID | Да | Уникальный идентификатор |
| decision_card_id | UUID | Да | Ссылка на Decision Card |
| user_id | UUID | Да | Ссылка на пользователя |
| action_id | UUID | Нет | Ссылка на действие |
| feedback_type | enum | Да | Тип: useful / not_useful / done / dismissed |
| reason | text | Нет | Причина оценки |
| created_at | datetime | Да | Дата создания |

### Связи
- оставлено на `Decision Card`
- оставлено пользователем `User`
- может относиться к `Action`

---

## 8. Data Source

### Назначение
Источник данных для сигналов. Описывает откуда поступают сырые сигналы.

### Поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| source_id | UUID | Да | Уникальный идентификатор |
| agency_id | UUID | Да | Ссылка на агентство |
| name | string | Да | Название источника |
| source_type | enum | Да | Тип: internal / market / behavioral / operational |
| trust_level | enum | Да | Уровень доверия: high / medium / low |
| config | JSON | Нет | Конфигурация подключения |
| is_active | boolean | Да | Активен ли источник |
| last_sync_at | datetime | Нет | Время последней синхронизации |
| created_at | datetime | Да | Дата создания |

### Связи
- принадлежит к `Agency`
- порождает много `Signal`

---

## Схема взаимосвязей между сущностями

```
┌─────────┐       ┌─────────┐       ┌───────────┐
│ Agency  │◄──────┤  User   │       │ Data      │
└────┬────┘       └─────────┘       │ Source    │
     │                              └────┬──────┘
     │                                   │
     │                                   │
     │    ┌─────────┐    ┌─────────┐     │
     └───►│ Signal  │◄───┤ Action  │◄────┘
          └────┬────┘    └────▲────┘
               │              │
               │              │
               ▼              │
          ┌───────────┐      │
          │ Decision  │──────┘
          │  Card     │
          └────┬──────┘
               │
               ▼
          ┌───────────┐
          │ Morning   │
          │ Brief     │
          └───────────┘

          ┌───────────┐
          │ Feedback  │
          └───────────┘
```

### Описание связей

- **Agency** → имеет много **User**
- **Agency** → имеет много **Signal**
- **Agency** → имеет много **Decision Card**
- **Agency** → имеет много **Morning Brief**
- **Agency** → имеет много **Data Source**

- **User** → оставляет много **Feedback**
- **User** → выполняет много **Action**

- **Data Source** → порождает много **Signal**

- **Signal** → порождает один **Decision Card**
- **Signal** → имеет один **Action**

- **Decision Card** → входит в **Morning Brief**
- **Decision Card** → имеет много **Feedback**
- **Decision Card** → порождает один **Action**

- **Action** → имеет много **Feedback**

---

## Примечания по MVP

- Все сущности содержат минимальный набор полей для работы системы.
- Поля `created_at` и `updated_at` присутствуют во всех сущностях для аудита.
- JSON-поля используются для гибкости конфигурации и разбивки оценок.
- Связи между сущностями построены так, чтобы поддерживать полный цикл: от сигнала до действия и обратной связи.

Следующий шаг — использовать эту модель данных для проектирования API-контрактов или первого технического спринта.