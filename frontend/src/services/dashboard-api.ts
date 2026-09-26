import {
  type BriefActionItem,
  type DashboardData,
  type DecisionCardFeedbackState,
  type DecisionCardItem,
  type KPIItem,
  type MorningBriefData,
  type SignalItem,
  type SignalKind,
  type SignalSeverity,
} from "../data/dashboard";
import { ApiClientError, apiClient } from "./api-client";

type SignalStatus =
  | "new"
  | "normalized"
  | "scored"
  | "filtered"
  | "rejected";

interface SignalResponseDto {
  signal_id: string;
  agency_id: string;
  source_id: string;
  signal_type: SignalKind;
  raw_data: Record<string, unknown>;
  status: SignalStatus;
  created_at: string;
  updated_at: string;
  is_processed: boolean;
  is_rejected: boolean;
  can_be_scored: boolean;
  can_be_filtered: boolean;
}

/** Разрешённые backend значения feedback (DecisionCardFeedbackState). */
export type DecisionCardFeedbackValue = Exclude<
  DecisionCardFeedbackState,
  "pending"
>;

/** Тело команды POST /morning-brief/persisted (контракт PersistedMorningBriefCreateDTO). */
export interface PersistedMorningBriefCreateCommand {
  agency_id: string;
  brief_date: string;
  signal_ids: string[];
  idempotency_key: string;
  trigger_type: "manual";
}

/** Ответ persisted-создания: только IDs, контент карточек читается отдельным GET. */
export interface PersistedMorningBriefCreateResponseDto {
  brief_id: string;
  brief_date: string;
  decision_card_groups: Array<{
    category: "opportunities" | "risks" | "market_insights";
    decision_card_ids: string[];
  }>;
  main_decision_card_id: string | null;
  replayed: boolean;
}

/** Persisted DecisionCard (контракт MorningBriefDecisionCardDTO). */
export interface PersistedDecisionCardDto {
  decision_card_id: string;
  card_type: string;
  title: string;
  summary: string;
  why_it_matters: string;
  what_to_do: string;
  deadline: string;
  money_effect_display: string;
  score: number;
  confidence: number;
  priority: string;
  status: string;
  feedback_state: DecisionCardFeedbackState;
}

/** Полное persisted-представление брифа (контракт MorningBriefReadDTO). */
export interface PersistedMorningBriefReadDto {
  brief_id: string;
  agency_id: string;
  brief_date: string;
  generated_at: string;
  status: string;
  summary_text: string;
  opportunity_cards: PersistedDecisionCardDto[];
  risk_cards: PersistedDecisionCardDto[];
  market_insight_cards: PersistedDecisionCardDto[];
  main_decision_card: PersistedDecisionCardDto | null;
}

/** Metadata-only запись истории брифов (контракт MorningBriefHistoryItemDTO). */
export interface MorningBriefHistoryItemDto {
  brief_id: string;
  brief_date: string;
  generated_at: string;
  status: string;
  summary_text: string;
  opportunity_count: number;
  risk_count: number;
  market_insight_count: number;
  total_card_count: number;
}

/** Ответ сохранения feedback (контракт DecisionCardFeedbackResponse). */
export interface DecisionCardFeedbackResponseDto {
  decision_card_id: string;
  status: string;
  feedback_state: DecisionCardFeedbackValue;
  updated_at: string;
}

function getString(data: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = data[key];

    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }

  return null;
}

function getNumber(data: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = data[key];

    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }

    if (typeof value === "string") {
      const parsed = Number(value.replace(/\s/g, "").replace(",", "."));

      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return null;
}

function formatMoney(value: number, kind: SignalKind): string {
  const prefix = kind === "risk" ? "-" : "+";

  return `${prefix}${Math.abs(value).toLocaleString("ru-RU")} ₽`;
}

function getImpact(signal: SignalResponseDto): string {
  const formatted = getString(
    signal.raw_data,
    "money_effect_display",
    "impact_display",
    "impact",
  );

  if (formatted) {
    return formatted;
  }

  const amount = getNumber(
    signal.raw_data,
    "money_effect",
    "potential_revenue",
    "cost_of_inaction",
    "amount",
  );

  return amount === null ? "Эффект не рассчитан" : formatMoney(amount, signal.signal_type);
}

function getSeverity(status: SignalStatus): SignalSeverity {
  if (status === "rejected") {
    return "low";
  }

  if (status === "filtered" || status === "scored") {
    return "high";
  }

  return "medium";
}

function getSignalTitle(signal: SignalResponseDto): string {
  return (
    getString(signal.raw_data, "title", "name", "event", "destination") ??
    `Сигнал ${signal.signal_type}`
  );
}

function getSignalSummary(signal: SignalResponseDto): string {
  return (
    getString(signal.raw_data, "summary", "description", "message") ??
    "Подробности доступны после обработки сигнала."
  );
}

function getSignalAction(signal: SignalResponseDto): string {
  return (
    getString(signal.raw_data, "recommended_action", "action", "next_step") ??
    "Ожидает обработки в revenue pipeline."
  );
}

function formatDate(value: string): string {
  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("ru-RU", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

function toSignalItem(signal: SignalResponseDto): SignalItem {
  return {
    id: signal.signal_id,
    title: getSignalTitle(signal),
    type: signal.signal_type,
    severity: getSeverity(signal.status),
    impact: getImpact(signal),
    deadline:
      getString(signal.raw_data, "deadline_display", "deadline", "due_at") ??
      "Не указан",
    source:
      getString(signal.raw_data, "source_display", "source_name", "source") ??
      signal.source_id,
    status: signal.status,
    summary: getSignalSummary(signal),
    action: getSignalAction(signal),
  };
}

function persistedCardToBriefAction(
  card: PersistedDecisionCardDto,
  kind: "opportunity" | "risk",
): BriefActionItem {
  return {
    id: card.decision_card_id,
    title: card.title,
    effect: card.money_effect_display,
    deadline: card.deadline,
    kind,
    description: card.what_to_do || card.summary,
  };
}

const PRIORITY_LABELS: Record<string, string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

function persistedCardToDecisionCard(
  card: PersistedDecisionCardDto,
): DecisionCardItem {
  const categoryByType: Record<string, DecisionCardItem["category"]> = {
    opportunity: "growth",
    risk: "retention",
    market_insight: "pricing",
    operational_insight: "operations",
  };

  return {
    id: card.decision_card_id,
    decisionCardId: card.decision_card_id,
    title: card.title,
    category: categoryByType[card.card_type] ?? "operations",
    impact: card.money_effect_display,
    confidence: `${Math.round(card.confidence * 100)}%`,
    horizon: card.deadline,
    owner: PRIORITY_LABELS[card.priority] ?? card.priority,
    summary: card.summary,
    steps: card.what_to_do
      .split(/\n|\d+\.\s/)
      .map((step) => step.trim())
      .filter(Boolean),
    feedbackState: card.feedback_state,
    status: card.status,
  };
}

function createEmptyMorningBrief() {
  const mainAction: BriefActionItem = {
    id: "no-main-action",
    title: "Нет действий на сегодня",
    effect: "0 ₽",
    deadline: "—",
    kind: "opportunity",
    description: "После появления обработанных сигналов здесь будет показано главное действие.",
  };

  return {
    title: "Утренний бриф",
    generatedAt: "Нет обработанных сигналов",
    summary: "Backend не вернул рекомендаций для утреннего брифа.",
    mainAction,
    opportunities: [],
    risks: [],
    marketNotes: [],
  };
}

function createKpis(
  signals: SignalResponseDto[],
  brief: PersistedMorningBriefReadDto | null,
): KPIItem[] {
  const activeSignals = signals.filter((signal) => !signal.is_rejected);
  const riskSignals = activeSignals.filter((signal) => signal.signal_type === "risk");
  const opportunitySignals = activeSignals.filter(
    (signal) => signal.signal_type === "opportunity",
  );
  const sourceCount = new Set(signals.map((signal) => signal.source_id)).size;

  return [
    {
      id: "pipeline-impact",
      label: "Возможности в pipeline",
      value: String(opportunitySignals.length),
      delta: brief
        ? `${brief.opportunity_cards.length} в утреннем брифе`
        : "Бриф ещё не сформирован",
      trend: "up",
      hint: "Количество сигналов типа opportunity из backend API",
    },
    {
      id: "risk-exposure",
      label: "Риски в pipeline",
      value: String(riskSignals.length),
      delta: brief ? `${brief.risk_cards.length} в утреннем брифе` : "Без оценки",
      trend: riskSignals.length > 0 ? "down" : "neutral",
      hint: "Количество сигналов типа risk из backend API",
    },
    {
      id: "active-signals",
      label: "Активные сигналы",
      value: String(activeSignals.length),
      delta: `${signals.length - activeSignals.length} отклонено`,
      trend: activeSignals.length > 0 ? "up" : "neutral",
      hint: "Сигналы, не отклонённые pipeline",
    },
    {
      id: "source-health",
      label: "Источники сигналов",
      value: String(sourceCount),
      delta: "По уникальным source_id",
      trend: "neutral",
      hint: "Текущий backend не предоставляет health-check источников",
    },
  ];
}

function buildDashboardData(
  signals: SignalResponseDto[],
  brief: PersistedMorningBriefReadDto | null,
): DashboardData {
  const briefData: MorningBriefData = brief
    ? {
        title: "Утренний бриф",
        generatedAt: `Сформирован ${formatDate(brief.generated_at)}`,
        summary:
          brief.summary_text ||
          "Бриф сформирован на основе текущих сигналов backend.",
        mainAction: brief.main_decision_card
          ? persistedCardToBriefAction(
              brief.main_decision_card,
              brief.main_decision_card.card_type === "risk" ? "risk" : "opportunity",
            )
          : createEmptyMorningBrief().mainAction,
        opportunities: brief.opportunity_cards.map((card) =>
          persistedCardToBriefAction(card, "opportunity"),
        ),
        risks: brief.risk_cards.map((card) =>
          persistedCardToBriefAction(card, "risk"),
        ),
        marketNotes: brief.market_insight_cards.map(
          (card) => `${card.title}: ${card.summary}`,
        ),
      }
    : createEmptyMorningBrief();

  const cards = brief
    ? [
        ...brief.opportunity_cards,
        ...brief.risk_cards,
        ...brief.market_insight_cards,
      ].map((card) => persistedCardToDecisionCard(card))
    : [];

  return {
    kpis: createKpis(signals, brief),
    signals: signals.map(toSignalItem),
    decisionCards: cards,
    morningBrief: briefData,
    sources: [],
    settings: [],
  };
}

/** Загружает metadata-историю и читает последний persisted бриф агентства. */
async function loadLatestPersistedBrief(
  agencyId: string,
): Promise<PersistedMorningBriefReadDto | null> {
  const history = await apiClient.get<MorningBriefHistoryItemDto[]>(
    `/agencies/${encodeURIComponent(agencyId)}/morning-briefs?limit=1&offset=0`,
  );
  const latest = history[0];

  if (!latest) {
    return null;
  }

  return apiClient.get<PersistedMorningBriefReadDto>(
    `/morning-brief/${encodeURIComponent(latest.brief_id)}?agency_id=${encodeURIComponent(agencyId)}`,
  );
}

/** Данные dashboard с последним persisted брифом (или пустым состоянием). */
export async function getDashboardData(agencyId: string): Promise<DashboardData> {
  const signals = await apiClient.get<SignalResponseDto[]>("/signals");
  const brief = await loadLatestPersistedBrief(agencyId);

  return buildDashboardData(signals, brief);
}

export interface PersistedBriefGenerationResult {
  data: DashboardData;
  /** Backend вернул replay существующего брифа по idempotency key. */
  replayed: boolean;
  /** Конфликт даты: показан уже существующий бриф вместо создания нового. */
  shownExisting: boolean;
}

function getTodayIsoDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function describePersistedCreateError(error: unknown): Error {
  if (error instanceof ApiClientError) {
    if (error.status === 403) {
      return new Error("Нет доступа к брифам этого рабочего пространства.");
    }
    if (error.status === 404) {
      return new Error("Часть сигналов не найдена в backend. Обновите данные и повторите.");
    }
    if (error.status === 400 || error.status === 422) {
      return new Error("Backend отклонил запрос на создание брифа.");
    }
    if (error.status === 503 || error.status === 0) {
      return new Error("Сервис генерации брифа временно недоступен. Повторите попытку позже.");
    }
  }

  return error instanceof Error && error.message
    ? new Error(error.message)
    : new Error("Не удалось сформировать бриф. Повторите попытку позже.");
}

/**
 * Создаёт persisted Morning Brief и читает его полное представление.
 * Create-ответ содержит только IDs, поэтому карточки всегда догружаются
 * отдельным GET read. 409 (бриф за эту дату уже существует из-за уникального
 * индекса agency_id + brief_date) не считается ошибкой: возвращается
 * существующий последний бриф через history + read.
 */
export async function createPersistedMorningBriefDashboardData(
  agencyId: string,
): Promise<PersistedBriefGenerationResult> {
  const signals = await apiClient.get<SignalResponseDto[]>("/signals");

  if (signals.length === 0) {
    throw new Error("Нет сигналов для формирования брифа. Дождитесь поступления данных из источников.");
  }

  let createResponse: PersistedMorningBriefCreateResponseDto;

  try {
    createResponse = await apiClient.post<
      PersistedMorningBriefCreateResponseDto,
      PersistedMorningBriefCreateCommand
    >("/morning-brief/persisted", {
      agency_id: agencyId,
      brief_date: getTodayIsoDate(),
      signal_ids: signals.map((signal) => signal.signal_id),
      idempotency_key: crypto.randomUUID(),
      trigger_type: "manual",
    });
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 409) {
      const existingBrief = await loadLatestPersistedBrief(agencyId);

      if (!existingBrief) {
        throw new Error("Бриф на эту дату уже существует, но загрузить сохранённую версию не удалось.");
      }

      return {
        data: buildDashboardData(signals, existingBrief),
        replayed: false,
        shownExisting: true,
      };
    }

    throw describePersistedCreateError(error);
  }

  let brief: PersistedMorningBriefReadDto;

  try {
    brief = await apiClient.get<PersistedMorningBriefReadDto>(
      `/morning-brief/${encodeURIComponent(createResponse.brief_id)}?agency_id=${encodeURIComponent(agencyId)}`,
    );
  } catch (error) {
    throw describePersistedCreateError(error);
  }

  return {
    data: buildDashboardData(signals, brief),
    replayed: createResponse.replayed,
    shownExisting: false,
  };
}

/** Сохраняет feedback persisted Decision Card через центральный ApiClient. */
export async function submitDecisionCardFeedback(
  agencyId: string,
  decisionCardId: string,
  feedbackState: DecisionCardFeedbackValue,
): Promise<DecisionCardFeedbackResponseDto> {
  return apiClient.post<
    DecisionCardFeedbackResponseDto,
    { feedback_state: DecisionCardFeedbackValue }
  >(
    `/decision-cards/${encodeURIComponent(decisionCardId)}/feedback?agency_id=${encodeURIComponent(agencyId)}`,
    { feedback_state: feedbackState },
  );
}
