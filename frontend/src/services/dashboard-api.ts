import {
  type BriefActionItem,
  type DashboardData,
  type DecisionCardItem,
  type KPIItem,
  type SignalItem,
  type SignalKind,
  type SignalSeverity,
} from "../data/dashboard";
import { apiClient } from "./api-client";

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

interface SignalCreateDto {
  agency_id: string;
  source_id: string;
  signal_type: SignalKind;
  raw_data: Record<string, unknown>;
}

interface DecisionCardDto {
  card_type:
    | "opportunity"
    | "risk"
    | "market_insight"
    | "operational_insight";
  title: string;
  summary: string;
  money_effect_display: string;
  importance_label: string;
  why_it_matters: string;
  what_to_do: string;
  deadline_display: string;
  confidence_display: string;
  source_display: string;
  status_display: string;
}

interface MorningBriefResponseDto {
  brief_id: string;
  date: string;
  generated_at: string;
  opportunities: DecisionCardDto[];
  risks: DecisionCardDto[];
  market_insights: DecisionCardDto[];
  main_action: DecisionCardDto | null;
  summary_text: string;
  stats: {
    total_cards_processed: number;
    opportunities_count: number;
    risks_count: number;
    market_insights_count: number;
  };
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

function toBriefAction(
  card: DecisionCardDto,
  id: string,
  kind: "opportunity" | "risk",
): BriefActionItem {
  return {
    id,
    title: card.title,
    effect: card.money_effect_display,
    deadline: card.deadline_display,
    kind,
    description: card.what_to_do || card.summary,
  };
}

function toDecisionCard(
  card: DecisionCardDto,
  id: string,
): DecisionCardItem {
  const categoryByType = {
    opportunity: "growth",
    risk: "retention",
    market_insight: "pricing",
    operational_insight: "operations",
  } as const;

  return {
    id,
    title: card.title,
    category: categoryByType[card.card_type],
    impact: card.money_effect_display,
    confidence: card.confidence_display,
    horizon: card.deadline_display,
    owner: card.status_display,
    summary: card.summary,
    steps: card.what_to_do
      .split(/\n|\d+\.\s/)
      .map((step) => step.trim())
      .filter(Boolean),
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
  brief: MorningBriefResponseDto | null,
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
        ? `${brief.stats.opportunities_count} в утреннем брифе`
        : "Бриф ещё не сформирован",
      trend: "up",
      hint: "Количество сигналов типа opportunity из backend API",
    },
    {
      id: "risk-exposure",
      label: "Риски в pipeline",
      value: String(riskSignals.length),
      delta: brief ? `${brief.stats.risks_count} в утреннем брифе` : "Без оценки",
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

async function requestMorningBrief(
  signals: SignalResponseDto[],
): Promise<MorningBriefResponseDto | null> {
  if (signals.length === 0) {
    return null;
  }

  const payload: SignalCreateDto[] = signals.map((signal) => ({
    agency_id: signal.agency_id,
    source_id: signal.source_id,
    signal_type: signal.signal_type,
    raw_data: signal.raw_data,
  }));

  return apiClient.post<MorningBriefResponseDto, SignalCreateDto[]>(
    "/morning-brief/generate",
    payload,
  );
}

function buildDashboardData(
  signals: SignalResponseDto[],
  morningBrief: MorningBriefResponseDto | null,
): DashboardData {
  const briefData = morningBrief
    ? {
        title: "Утренний бриф",
        generatedAt: `Сформирован ${formatDate(morningBrief.generated_at)}`,
        summary:
          morningBrief.summary_text ||
          "Бриф сформирован на основе текущих сигналов backend.",
        mainAction: morningBrief.main_action
          ? toBriefAction(
              morningBrief.main_action,
              `${morningBrief.brief_id}-main`,
              morningBrief.main_action.card_type === "risk" ? "risk" : "opportunity",
            )
          : createEmptyMorningBrief().mainAction,
        opportunities: morningBrief.opportunities.map((card, index) =>
          toBriefAction(card, `${morningBrief.brief_id}-opportunity-${index}`, "opportunity"),
        ),
        risks: morningBrief.risks.map((card, index) =>
          toBriefAction(card, `${morningBrief.brief_id}-risk-${index}`, "risk"),
        ),
        marketNotes: morningBrief.market_insights.map(
          (card) => `${card.title}: ${card.summary}`,
        ),
      }
    : createEmptyMorningBrief();

  const cards = morningBrief
    ? [
        ...morningBrief.opportunities,
        ...morningBrief.risks,
        ...morningBrief.market_insights,
      ].map((card, index) => toDecisionCard(card, `${morningBrief.brief_id}-${index}`))
    : [];

  return {
    kpis: createKpis(signals, morningBrief),
    signals: signals.map(toSignalItem),
    decisionCards: cards,
    morningBrief: briefData,
    sources: [],
    settings: [],
  };
}

export async function getDashboardData(): Promise<DashboardData> {
  const signals = await apiClient.get<SignalResponseDto[]>("/signals");

  return buildDashboardData(signals, null);
}

export async function generateMorningBriefDashboardData(): Promise<DashboardData> {
  const signals = await apiClient.get<SignalResponseDto[]>("/signals");
  const morningBrief = await requestMorningBrief(signals);

  return buildDashboardData(signals, morningBrief);
}
