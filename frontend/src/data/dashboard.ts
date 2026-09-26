export type NavigationPage =
  | "dashboard"
  | "signals"
  | "decision-cards"
  | "morning-brief"
  | "sources"
  | "settings";

export type SignalSeverity = "high" | "medium" | "low";
export type SignalKind = "opportunity" | "risk" | "market" | "operational";
export type SourceHealth = "online" | "warning" | "offline";

export interface KPIItem {
  id: string;
  label: string;
  value: string;
  delta: string;
  trend: "up" | "down" | "neutral";
  hint: string;
}

export interface SignalItem {
  id: string;
  title: string;
  type: SignalKind;
  severity: SignalSeverity;
  impact: string;
  deadline: string;
  source: string;
  status: string;
  summary: string;
  action: string;
}

/** Разрешённые состояния feedback persisted Decision Card (backend enum + локальное pending). */
export type DecisionCardFeedbackState = "pending" | "accepted" | "dismissed" | "completed";

export interface DecisionCardItem {
  id: string;
  title: string;
  category: "growth" | "retention" | "pricing" | "operations";
  impact: string;
  confidence: string;
  horizon: string;
  owner: string;
  summary: string;
  steps: string[];
  /** Backend UUID persisted-карточки; основа для feedback-запросов. */
  decisionCardId?: string;
  feedbackState?: DecisionCardFeedbackState;
  status?: string;
}

export interface BriefActionItem {
  id: string;
  title: string;
  effect: string;
  deadline: string;
  kind: "opportunity" | "risk";
  description: string;
}

export interface MorningBriefData {
  title: string;
  generatedAt: string;
  summary: string;
  mainAction: BriefActionItem;
  opportunities: BriefActionItem[];
  risks: BriefActionItem[];
  marketNotes: string[];
}

export interface SourceStatusItem {
  id: string;
  name: string;
  type: string;
  status: SourceHealth;
  lastSync: string;
  freshness: string;
  notes: string;
}

export interface SettingsSection {
  id: string;
  title: string;
  description: string;
  items: Array<{
    id: string;
    label: string;
    value: string;
    hint: string;
  }>;
}

export interface DashboardData {
  kpis: KPIItem[];
  signals: SignalItem[];
  decisionCards: DecisionCardItem[];
  morningBrief: MorningBriefData;
  sources: SourceStatusItem[];
  settings: SettingsSection[];
}

export const navigationItems: Array<{
  id: NavigationPage;
  label: string;
  description: string;
}> = [
  {
    id: "dashboard",
    label: "Dashboard",
    description: "Общая картина по выручке и рискам",
  },
  {
    id: "signals",
    label: "Signals",
    description: "Сырые и обработанные сигналы",
  },
  {
    id: "decision-cards",
    label: "Decision Cards",
    description: "Конкретные рекомендации для действий",
  },
  {
    id: "morning-brief",
    label: "Morning Brief",
    description: "Утренний бриф для владельца агентства",
  },
  {
    id: "sources",
    label: "Sources",
    description: "Состояние источников данных",
  },
  {
    id: "settings",
    label: "Settings",
    description: "Параметры dashboard и API",
  },
];

export const dashboardMockData: DashboardData = {
  kpis: [
    {
      id: "pipeline-impact",
      label: "Потенциал выручки",
      value: "+420 000 ₽",
      delta: "+18% за неделю",
      trend: "up",
      hint: "Суммарный потенциал топовых возможностей",
    },
    {
      id: "risk-exposure",
      label: "Под риском",
      value: "-135 000 ₽",
      delta: "-12% к вчера",
      trend: "down",
      hint: "Потенциальные потери без действия",
    },
    {
      id: "active-signals",
      label: "Активные сигналы",
      value: "28",
      delta: "+6 новых",
      trend: "up",
      hint: "Сигналы, требующие внимания сегодня",
    },
    {
      id: "source-health",
      label: "Источники онлайн",
      value: "8 / 10",
      delta: "2 требуют проверки",
      trend: "neutral",
      hint: "Подключения к внешним и внутренним источникам",
    },
  ],
  signals: [
    {
      id: "sig-001",
      title: "Раннее бронирование Турции",
      type: "opportunity",
      severity: "high",
      impact: "+85 000 ₽",
      deadline: "Сегодня до 18:00",
      source: "CRM + поисковые тренды",
      status: "Готов к действию",
      summary: "Спрос ускорился, а цены поставщиков вырастут в течение 48 часов.",
      action: "Запустить рассылку по базе и передать лиды менеджерам.",
    },
    {
      id: "sig-002",
      title: "Рост цен на авиабилеты в Египет",
      type: "risk",
      severity: "high",
      impact: "-60 000 ₽",
      deadline: "Сегодня до 14:00",
      source: "OTA + авиапрайсы",
      status: "Нужна реакция",
      summary: "По ключевому направлению ожидается рост себестоимости уже завтра.",
      action: "Пересчитать маржу по активным предложениям и предупредить менеджеров.",
    },
    {
      id: "sig-003",
      title: "Интерес к ОАЭ в корпоративном сегменте",
      type: "market",
      severity: "medium",
      impact: "+45 000 ₽",
      deadline: "В течение 3 дней",
      source: "Email + сайт",
      status: "На проверке",
      summary: "Увеличилось число просмотров корпоративных подборок и запросов на инвойсы.",
      action: "Подготовить короткий оффер для B2B-клиентов и прозвонить горячий список.",
    },
    {
      id: "sig-004",
      title: "Долгий ответ по входящим заявкам",
      type: "operational",
      severity: "medium",
      impact: "+20 000 ₽",
      deadline: "На этой неделе",
      source: "Внутренний SLA",
      status: "Планируется",
      summary: "Среднее время ответа выросло до 38 минут и давит на конверсию.",
      action: "Перераспределить дежурства и включить автораздачу заявок.",
    },
    {
      id: "sig-005",
      title: "Снижение интереса к автобусным турам",
      type: "market",
      severity: "low",
      impact: "-12 000 ₽",
      deadline: "Без жёсткого дедлайна",
      source: "Wordstat",
      status: "Наблюдение",
      summary: "Тренд снижается, но прямого срочного действия пока не требует.",
      action: "Отслеживать динамику и не увеличивать рекламный бюджет в сегменте.",
    },
  ],
  decisionCards: [
    {
      id: "card-001",
      title: "Реактивировать прошлогоднюю базу по Турции",
      category: "growth",
      impact: "+85 000 ₽",
      confidence: "72%",
      horizon: "24 часа",
      owner: "Отдел продаж",
      summary: "Быстрая выручка за счёт тёплой базы и ограниченного окна по цене.",
      steps: [
        "Собрать сегмент клиентов, бронировавших Турцию за последние 12 месяцев.",
        "Отправить email и Telegram-оффер с дедлайном до вечера.",
        "Назначить обзвон топ-20 клиентов с наибольшим средним чеком.",
      ],
    },
    {
      id: "card-002",
      title: "Защитить маржу по Египту",
      category: "pricing",
      impact: "-60 000 ₽",
      confidence: "81%",
      horizon: "12 часов",
      owner: "Коммерческий отдел",
      summary: "Риск потери маржи выше средней и уже влияет на активные предложения.",
      steps: [
        "Пересчитать текущие подборки с учётом новых тарифов.",
        "Заморозить старые цены в рассылках и рекламе.",
        "Обновить скрипт менеджеров для объяснения корректировки цены.",
      ],
    },
    {
      id: "card-003",
      title: "Сократить время реакции на входящие лиды",
      category: "operations",
      impact: "+20 000 ₽",
      confidence: "64%",
      horizon: "3 дня",
      owner: "Руководитель отдела",
      summary: "Даже небольшое сокращение SLA даст рост конверсии на горячих заявках.",
      steps: [
        "Выделить ответственного на утренний пик обращений.",
        "Настроить мгновенное уведомление в рабочий чат.",
        "Проверить SLA в конце дня и сравнить с базовым уровнем.",
      ],
    },
  ],
  morningBrief: {
    title: "Утренний бриф",
    generatedAt: "17 июля, 08:00",
    summary: "Сегодня есть одно сильное окно роста и один критический риск по марже.",
    mainAction: {
      id: "brief-main",
      title: "Запустить кампанию по раннему бронированию Турции",
      effect: "+85 000 ₽",
      deadline: "Сегодня до 18:00",
      kind: "opportunity",
      description: "Самое быстрое действие с высокой вероятностью конверсии и понятной базой клиентов.",
    },
    opportunities: [
      {
        id: "brief-op-1",
        title: "Раннее бронирование Турции",
        effect: "+85 000 ₽",
        deadline: "Сегодня",
        kind: "opportunity",
        description: "Тёплая база и понятный оффер с ограничением по времени.",
      },
      {
        id: "brief-op-2",
        title: "Оффер для корпоративных клиентов по ОАЭ",
        effect: "+45 000 ₽",
        deadline: "3 дня",
        kind: "opportunity",
        description: "Сегмент начал прогреваться, можно быстро протестировать спрос.",
      },
    ],
    risks: [
      {
        id: "brief-risk-1",
        title: "Рост себестоимости по Египту",
        effect: "-60 000 ₽",
        deadline: "Сегодня до 14:00",
        kind: "risk",
        description: "Нужно защитить маржу до обновления цен у поставщиков.",
      },
    ],
    marketNotes: [
      "По Турции рост поискового спроса составил +34% за 7 дней.",
      "По Египту поставщики обновляют цены в течение ближайших суток.",
      "Доля мобильного трафика выросла до 68%, акцент на быстрые карточки оффера.",
    ],
  },
  sources: [
    {
      id: "source-1",
      name: "CRM сделки",
      type: "Внутренний источник",
      status: "online",
      lastSync: "5 минут назад",
      freshness: "Актуально",
      notes: "Сделки и история клиентов обновляются стабильно.",
    },
    {
      id: "source-2",
      name: "OTA прайсы",
      type: "Рыночный источник",
      status: "online",
      lastSync: "12 минут назад",
      freshness: "Актуально",
      notes: "Прайсы по основным направлениям доступны без задержек.",
    },
    {
      id: "source-3",
      name: "Email аналитика",
      type: "Поведенческий источник",
      status: "warning",
      lastSync: "48 минут назад",
      freshness: "Нужна проверка",
      notes: "Есть задержка по открываемости последних рассылок.",
    },
    {
      id: "source-4",
      name: "Telegram лиды",
      type: "Поведенческий источник",
      status: "online",
      lastSync: "8 минут назад",
      freshness: "Актуально",
      notes: "Новые входящие обращения приходят без ошибок.",
    },
    {
      id: "source-5",
      name: "Wordstat тренды",
      type: "Рыночный источник",
      status: "offline",
      lastSync: "3 часа назад",
      freshness: "Нет данных",
      notes: "Требуется переподключение или повторный сбор.",
    },
  ],
  settings: [
    {
      id: "api",
      title: "API и режим данных",
      description: "Настройки подключения frontend к backend и mock-режиму.",
      items: [
        {
          id: "mode",
          label: "Режим данных",
          value: "Mock API",
          hint: "Пока frontend работает на встроенных данных и готов к переключению на backend.",
        },
        {
          id: "signals-endpoint",
          label: "Signals endpoint",
          value: "/signals",
          hint: "Текущий маршрут backend для списка сигналов.",
        },
        {
          id: "brief-endpoint",
          label: "Morning brief endpoint",
          value: "/morning-brief/generate",
          hint: "Маршрут для генерации брифа из списка сигналов.",
        },
      ],
    },
    {
      id: "display",
      title: "Параметры интерфейса",
      description: "Базовые опции отображения и приоритетов dashboard.",
      items: [
        {
          id: "theme",
          label: "Тема",
          value: "Светлая",
          hint: "Текущий sprint использует современную светлую тему.",
        },
        {
          id: "layout",
          label: "Навигация",
          value: "Sidebar + Header",
          hint: "Адаптивный layout для desktop и mobile.",
        },
        {
          id: "priority",
          label: "Фокус dashboard",
          value: "Риски и выручка",
          hint: "На первом экране показываются деньги, дедлайны и действия.",
        },
      ],
    },
  ],
};

export const topOpportunities = dashboardMockData.signals.filter(
  (signal) => signal.type === "opportunity"
);

export const topRisks = dashboardMockData.signals.filter(
  (signal) => signal.type === "risk"
);