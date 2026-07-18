import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  BadgeCheck,
  CircleAlert,
  ArrowUpRight,
  BarChart3,
  Bell,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Database,
  FileClock,
  FileText,
  Inbox,
  LayoutDashboard,
  LoaderCircle,
  Mail,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Settings2,
  Send,
  ShieldAlert,
  Sparkles,
  Target,
  X,
  XCircle,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  navigationItems,
  type DashboardData,
  type NavigationPage,
  type SignalItem,
} from "./data/dashboard";
import {
  generateMorningBriefDashboardData,
  getDashboardData,
} from "./services/dashboard-api";

const navigationIcons: Record<NavigationPage, LucideIcon> = {
  dashboard: LayoutDashboard,
  signals: Activity,
  "decision-cards": FileText,
  "morning-brief": Sparkles,
  sources: Database,
  settings: Settings2,
};

const pageTitles: Record<NavigationPage, string> = {
  dashboard: "Dashboard",
  signals: "Signals",
  "decision-cards": "Decision Cards",
  "morning-brief": "Morning Brief",
  sources: "Sources",
  settings: "Settings",
};

const pageDescriptions: Record<NavigationPage, string> = {
  dashboard: "Деньги, риски и приоритетные действия на сегодня.",
  signals: "Сигналы, которые прошли первичную проверку и требуют решения.",
  "decision-cards": "Конкретные карточки действий с деньгами, сроком и владельцем.",
  "morning-brief": "Короткий управленческий бриф, который помогает начать день с главного.",
  sources: "Контроль свежести и доступности данных для Revenue Engine.",
  settings: "Параметры интерфейса и подготовка к подключению backend API.",
};

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type ToastMessage = {
  id: number;
  title: string;
  description?: string;
  kind: "success" | "error";
};

type LastRun = {
  generatedAt: string;
  status: "success" | "error";
  durationMs: number;
  signalCount: number;
  decisionCardCount: number;
};

type WidgetName = "signals" | "opportunities" | "morningBrief" | "sources";

function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  compact = false,
}: {
  icon?: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={classNames(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50/70 text-center",
        compact ? "px-4 py-6" : "px-5 py-10",
      )}
    >
      <span className="grid size-10 place-items-center rounded-xl bg-white text-slate-400 shadow-sm">
        <Icon size={20} />
      </span>
      <h3 className="mt-3 text-sm font-semibold text-slate-800">{title}</h3>
      <p className="mt-1 max-w-sm text-sm leading-5 text-slate-500">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

function WidgetRefreshButton({
  label,
  isLoading,
  onClick,
}: {
  label: string;
  isLoading: boolean;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      disabled={isLoading}
      onClick={onClick}
      className="grid size-10 shrink-0 place-items-center rounded-xl border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:cursor-wait disabled:opacity-60"
    >
      <RefreshCw className={isLoading ? "animate-spin" : ""} size={16} />
    </button>
  );
}

function ToastViewport({
  toasts,
  onDismiss,
}: {
  toasts: ToastMessage[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-3 sm:inset-x-auto sm:right-6 sm:w-[390px]"
    >
      {toasts.map((toast) => {
        const isSuccess = toast.kind === "success";
        const Icon = isSuccess ? BadgeCheck : CircleAlert;

        return (
          <div
            key={toast.id}
            role="status"
            className={classNames(
              "pointer-events-auto flex w-full items-start gap-3 rounded-2xl border bg-white p-4 shadow-xl",
              isSuccess ? "border-emerald-200" : "border-rose-200",
            )}
          >
            <span className={classNames("mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg", isSuccess ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-600")}>
              <Icon size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-900">{toast.title}</p>
              {toast.description ? <p className="mt-1 text-sm leading-5 text-slate-500">{toast.description}</p> : null}
            </div>
            <button
              aria-label="Закрыть уведомление"
              onClick={() => onDismiss(toast.id)}
              className="grid size-8 shrink-0 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <X size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

function getSignalStyle(signal: SignalItem) {
  if (signal.type === "risk") {
    return {
      icon: ShieldAlert,
      label: "Риск",
      iconClass: "bg-rose-50 text-rose-600",
      badgeClass: "border-rose-100 bg-rose-50 text-rose-700",
    };
  }

  if (signal.type === "opportunity") {
    return {
      icon: Target,
      label: "Возможность",
      iconClass: "bg-emerald-50 text-emerald-600",
      badgeClass: "border-emerald-100 bg-emerald-50 text-emerald-700",
    };
  }

  if (signal.type === "operational") {
    return {
      icon: Zap,
      label: "Операции",
      iconClass: "bg-violet-50 text-violet-600",
      badgeClass: "border-violet-100 bg-violet-50 text-violet-700",
    };
  }

  return {
    icon: BarChart3,
    label: "Рынок",
    iconClass: "bg-sky-50 text-sky-600",
    badgeClass: "border-sky-100 bg-sky-50 text-sky-700",
  };
}

function Sidebar({
  activePage,
  isOpen,
  onNavigate,
  onClose,
}: {
  activePage: NavigationPage;
  isOpen: boolean;
  onNavigate: (page: NavigationPage) => void;
  onClose: () => void;
}) {
  return (
    <>
      {isOpen ? (
        <button
          aria-label="Закрыть меню"
          className="fixed inset-0 z-30 bg-slate-950/30 lg:hidden"
          onClick={onClose}
        />
      ) : null}
      <aside
        className={classNames(
          "fixed inset-y-0 left-0 z-40 flex w-[272px] flex-col border-r border-slate-200 bg-white px-4 py-5 transition-transform duration-200 lg:translate-x-0",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex items-center justify-between px-2">
          <button
            className="flex items-center gap-3 rounded-xl text-left focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
            onClick={() => onNavigate("dashboard")}
          >
            <span className="grid size-10 place-items-center rounded-xl bg-slate-950 text-white shadow-sm">
              <CircleDollarSign size={22} strokeWidth={2.4} />
            </span>
            <span>
              <span className="block text-sm font-semibold tracking-tight text-slate-950">
                Travel Revenue AI
              </span>
              <span className="block text-xs text-slate-500">Revenue cockpit</span>
            </span>
          </button>
          <button
            aria-label="Закрыть боковое меню"
            className="grid size-10 place-items-center rounded-xl text-slate-500 hover:bg-slate-100 lg:hidden"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>

        <nav aria-label="Основная навигация" className="mt-9 space-y-1">
          {navigationItems.map((item) => {
            const Icon = navigationIcons[item.id];
            const isActive = activePage === item.id;

            return (
              <button
                key={item.id}
                className={classNames(
                  "flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2",
                  isActive
                    ? "bg-slate-950 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                )}
                onClick={() => {
                  onNavigate(item.id);
                  onClose();
                }}
              >
                <Icon size={18} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="mt-auto rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
            <CheckCircle2 size={17} />
            Система активна
          </div>
          <p className="mt-2 text-xs leading-5 text-emerald-800">
            Revenue Engine просканировал источники и подготовил рекомендации.
          </p>
          <button
            className="mt-3 inline-flex min-h-10 items-center gap-1 text-xs font-semibold text-emerald-800 underline decoration-emerald-300 underline-offset-4 hover:text-emerald-950"
            onClick={() => onNavigate("sources")}
          >
            Проверить источники <ChevronRight size={14} />
          </button>
        </div>
      </aside>
    </>
  );
}

function Header({
  activePage,
  onMenuClick,
  onRefresh,
  isLoading,
}: {
  activePage: NavigationPage;
  onMenuClick: () => void;
  onRefresh: () => void;
  isLoading: boolean;
}) {
  return (
    <header className="sticky top-0 z-20 flex min-h-[76px] items-center justify-between border-b border-slate-200 bg-slate-50/90 px-4 backdrop-blur sm:px-6 lg:px-10">
      <div className="flex min-w-0 items-center gap-3">
        <button
          aria-label="Открыть меню"
          className="grid size-11 shrink-0 place-items-center rounded-xl text-slate-600 hover:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 lg:hidden"
          onClick={onMenuClick}
        >
          <Menu size={21} />
        </button>
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold tracking-tight text-slate-950 sm:text-xl">
            {pageTitles[activePage]}
          </p>
          <p className="hidden truncate text-sm text-slate-500 sm:block">
            {pageDescriptions[activePage]}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <button
          aria-label="Обновить данные"
          disabled={isLoading}
          className="grid size-11 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:cursor-wait disabled:opacity-60"
          onClick={onRefresh}
        >
          <RefreshCw className={isLoading ? "animate-spin" : ""} size={18} />
        </button>
        <button
          aria-label="Уведомления"
          className="relative grid size-11 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-slate-300 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <Bell size={18} />
          <span className="absolute right-2 top-2 size-2 rounded-full bg-rose-500 ring-2 ring-white" />
        </button>
        <div className="hidden items-center gap-3 rounded-xl border border-slate-200 bg-white py-1.5 pl-2 pr-3 shadow-sm sm:flex">
          <span className="grid size-8 place-items-center rounded-lg bg-slate-950 text-xs font-bold text-white">
            АБ
          </span>
          <span className="text-left">
            <span className="block text-xs font-semibold text-slate-900">Алексей Белов</span>
            <span className="block text-[11px] text-slate-500">Владелец агентства</span>
          </span>
        </div>
      </div>
    </header>
  );
}

function PageIntro({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">{eyebrow}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">{title}</h1>
        <div className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">{children}</div>
      </div>
      {action}
    </section>
  );
}

function KPICards({ data }: { data: DashboardData }) {
  return (
    <section aria-label="Ключевые показатели" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {data.kpis.map((kpi) => {
        const isUp = kpi.trend === "up";
        const isDown = kpi.trend === "down";
        const TrendIcon = isUp ? ArrowUpRight : isDown ? ArrowDownRight : Activity;

        return (
          <article key={kpi.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-slate-500">{kpi.label}</p>
              <span
                className={classNames(
                  "grid size-8 place-items-center rounded-lg",
                  isUp ? "bg-emerald-50 text-emerald-600" : isDown ? "bg-rose-50 text-rose-600" : "bg-slate-100 text-slate-500"
                )}
              >
                <TrendIcon size={16} />
              </span>
            </div>
            <p className="mt-4 text-2xl font-semibold tracking-tight text-slate-950">{kpi.value}</p>
            <p className="mt-2 text-xs font-medium text-slate-500">{kpi.delta}</p>
            <p className="mt-4 border-t border-slate-100 pt-3 text-xs leading-5 text-slate-400">{kpi.hint}</p>
          </article>
        );
      })}
    </section>
  );
}

function SignalRow({ signal, onOpen }: { signal: SignalItem; onOpen: () => void }) {
  const style = getSignalStyle(signal);
  const Icon = style.icon;

  return (
    <article className="flex gap-3 border-b border-slate-100 py-4 last:border-0 first:pt-0">
      <span className={classNames("mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl", style.iconClass)}>
        <Icon size={18} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <h3 className="font-semibold text-slate-900">{signal.title}</h3>
          <span className={classNames("rounded-full border px-2.5 py-1 text-xs font-semibold", style.badgeClass)}>
            {signal.impact}
          </span>
        </div>
        <p className="mt-1 text-sm leading-5 text-slate-500">{signal.summary}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-slate-500">
          <span className="inline-flex items-center gap-1"><Clock3 size={13} /> {signal.deadline}</span>
          <span className="hidden h-1 w-1 rounded-full bg-slate-300 sm:block" />
          <span>{signal.source}</span>
        </div>
      </div>
      <button
        className="grid size-10 shrink-0 place-items-center self-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        aria-label={`Открыть сигнал: ${signal.title}`}
        onClick={onOpen}
      >
        <ChevronRight size={18} />
      </button>
    </article>
  );
}

function RecentSignals({
  data,
  onNavigate,
  onRefresh,
  isRefreshing,
}: {
  data: DashboardData;
  onNavigate: (page: NavigationPage) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  const signals = data.signals.slice(0, 4);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-slate-950">Последние сигналы</h2>
          <p className="mt-1 text-sm text-slate-500">Что изменилось в бизнесе и рынке.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="text-sm font-semibold text-emerald-700 hover:text-emerald-900" onClick={() => onNavigate("signals")}>
            Все сигналы
          </button>
          <WidgetRefreshButton label="Обновить последние сигналы" isLoading={isRefreshing} onClick={onRefresh} />
        </div>
      </div>
      <div className="mt-5">
        {signals.length > 0 ? (
          signals.map((signal) => (
            <SignalRow key={signal.id} signal={signal} onOpen={() => onNavigate("signals")} />
          ))
        ) : (
          <EmptyState
            icon={Activity}
            compact
            title="Нет сигналов"
            description="Пока не найдено ни одного сигнала. Нажмите «Сгенерировать Morning Brief» или дождитесь следующего запуска."
          />
        )}
      </div>
    </section>
  );
}

function PriorityList({
  title,
  subtitle,
  items,
  isRisk,
  onNavigate,
  onRefresh,
  isRefreshing,
}: {
  title: string;
  subtitle: string;
  items: SignalItem[];
  isRisk?: boolean;
  onNavigate: (page: NavigationPage) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className={classNames("grid size-10 place-items-center rounded-xl", isRisk ? "bg-rose-50 text-rose-600" : "bg-emerald-50 text-emerald-600")}>
            {isRisk ? <AlertTriangle size={20} /> : <Target size={20} />}
          </span>
          <div>
            <h2 className="text-base font-semibold text-slate-950">{title}</h2>
            <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
          </div>
        </div>
        <WidgetRefreshButton label={`Обновить: ${title}`} isLoading={isRefreshing} onClick={onRefresh} />
      </div>
      <div className="mt-5 space-y-3">
        {items.length > 0 ? (
          items.map((item) => (
            <button
              key={item.id}
              className="w-full rounded-xl border border-slate-100 p-4 text-left transition hover:border-slate-200 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              onClick={() => onNavigate("decision-cards")}
            >
              <div className="flex items-start justify-between gap-3">
                <span className="font-semibold text-slate-900">{item.title}</span>
                <span className={classNames("whitespace-nowrap text-sm font-bold", isRisk ? "text-rose-600" : "text-emerald-600")}>{item.impact}</span>
              </div>
              <span className="mt-2 block text-xs text-slate-500">{item.deadline}</span>
            </button>
          ))
        ) : (
          <EmptyState
            icon={isRisk ? ShieldAlert : Target}
            compact
            title={isRisk ? "Нет рисков" : "Нет возможностей"}
            description={isRisk ? "Сейчас в потоке нет рисков, требующих отдельного действия." : "Пока нет возможностей, прошедших фильтрацию."}
          />
        )}
      </div>
    </section>
  );
}

function MorningBriefCard({
  data,
  onNavigate,
  onGenerate,
  isGenerating,
  lastGeneratedAt,
  onRefresh,
}: {
  data: DashboardData;
  onNavigate: (page: NavigationPage) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  lastGeneratedAt: string | null;
  onRefresh: () => void;
}) {
  const brief = data.morningBrief;

  return (
    <section className="overflow-hidden rounded-2xl bg-slate-950 p-5 text-white shadow-card sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-emerald-300">
            <Sparkles size={18} />
            <span className="text-xs font-semibold uppercase tracking-[0.14em]">Утренний бриф</span>
          </div>
          <h2 className="mt-3 text-xl font-semibold tracking-tight">{brief.mainAction.title}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">{brief.mainAction.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <WidgetRefreshButton label="Обновить Morning Brief" isLoading={isGenerating} onClick={onRefresh} />
          <span className="rounded-xl bg-white/10 px-3 py-2 text-sm font-semibold text-emerald-300">{brief.mainAction.effect}</span>
        </div>
      </div>
      <div className="mt-5 flex flex-col gap-4 border-t border-white/10 pt-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-300">
          <span className="inline-flex items-center gap-2"><Clock3 size={16} /> Дедлайн: {brief.mainAction.deadline}</span>
          <span aria-live="polite" className="inline-flex items-center gap-2 text-xs text-slate-400">
            <RefreshCw size={14} />
            {lastGeneratedAt ? `Последняя генерация: ${lastGeneratedAt}` : "Бриф ещё не генерировался вручную"}
          </span>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
          <button
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-white/20 px-4 text-sm font-semibold text-white transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-slate-950 disabled:cursor-wait disabled:opacity-60"
            disabled={isGenerating}
            onClick={onGenerate}
          >
            <RefreshCw className={isGenerating ? "animate-spin" : ""} size={16} />
            {isGenerating ? "Генерируем бриф…" : "Сгенерировать Morning Brief сейчас"}
          </button>
          <button
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-white px-4 text-sm font-semibold text-slate-950 transition hover:bg-emerald-50 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-slate-950"
            disabled={isGenerating}
            onClick={() => onNavigate("morning-brief")}
          >
            Открыть бриф <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </section>
  );
}

function SourceStatus({
  data,
  onNavigate,
  onRefresh,
  isRefreshing,
}: {
  data: DashboardData;
  onNavigate: (page: NavigationPage) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  const emailSource = data.sources.find((source) => /email/i.test(`${source.name} ${source.type}`));
  const telegramSource = data.sources.find((source) => /telegram/i.test(`${source.name} ${source.type}`));
  const sourceItems = [
    { id: "email", label: "Email", icon: Mail, source: emailSource },
    { id: "telegram", label: "Telegram", icon: Send, source: telegramSource },
  ];

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-slate-950">Статус источников</h2>
          <p className="mt-1 text-sm text-slate-500">Доступность Email и Telegram по существующим данным.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="text-sm font-semibold text-emerald-700 hover:text-emerald-900" onClick={() => onNavigate("sources")}>
            Все источники
          </button>
          <WidgetRefreshButton label="Обновить статусы источников" isLoading={isRefreshing} onClick={onRefresh} />
        </div>
      </div>
      <div className="mt-5 space-y-3">
        {sourceItems.map(({ id, label, icon: Icon, source }) => {
          const status = source?.status;
          const isOk = status === "online";
          const isWarning = status === "warning";
          const statusLabel = !source ? "Не поддерживается" : isOk ? "OK" : isWarning ? "Нет новых данных" : "Ошибка";

          return (
            <div key={id} className="flex items-center gap-3 rounded-xl border border-slate-100 p-3">
              <span className={classNames("grid size-9 place-items-center rounded-lg", isOk ? "bg-emerald-50 text-emerald-600" : isWarning ? "bg-amber-50 text-amber-600" : "bg-slate-100 text-slate-500")}>
                <Icon size={17} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-800">{label}</p>
                <p className="truncate text-xs text-slate-500">{source?.lastSync ?? "Backend не передаёт статус источника"}</p>
              </div>
              <span className={classNames("inline-flex items-center gap-1.5 text-xs font-semibold", isOk ? "text-emerald-700" : isWarning ? "text-amber-700" : "text-slate-500")}>
                <span className={classNames("size-2 rounded-full", isOk ? "bg-emerald-500" : isWarning ? "bg-amber-500" : source ? "bg-rose-500" : "bg-slate-300")} />
                {statusLabel}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ActivityMetrics({ data }: { data: DashboardData }) {
  const opportunities = data.signals.filter((signal) => signal.type === "opportunity").length;
  const risks = data.signals.filter((signal) => signal.type === "risk").length;
  const processed = data.signals.filter((signal) => !/new|normalized/i.test(signal.status)).length;

  const items = [
    { label: "Новых сигналов", value: data.signals.filter((signal) => signal.status === "new").length || "—", icon: Activity },
    { label: "Обработано", value: processed || "—", icon: CheckCircle2 },
    { label: "Decision Cards", value: data.decisionCards.length || "—", icon: FileText },
    { label: "Возможностей", value: opportunities || "—", icon: Target },
    { label: "Рисков", value: risks || "—", icon: ShieldAlert },
  ];

  return (
    <section aria-label="Активность Revenue Engine" className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {items.map(({ label, value, icon: Icon }) => (
        <article key={label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
          <Icon className="text-slate-400" size={17} />
          <p className="mt-3 text-xl font-semibold tracking-tight text-slate-950">{value}</p>
          <p className="mt-1 text-xs font-medium text-slate-500">{label}</p>
        </article>
      ))}
    </section>
  );
}

function LastRunCard({ lastRun }: { lastRun: LastRun | null }) {
  if (!lastRun) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
        <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-slate-500"><FileClock size={20} /></span>
          <div><h2 className="text-base font-semibold text-slate-950">Последний запуск</h2><p className="mt-1 text-sm text-slate-500">История запусков пока не передаётся backend.</p></div>
        </div>
        <div className="mt-5">
          <EmptyState icon={FileClock} compact title="Нет данных о запуске" description="Сформируйте Morning Brief — здесь появятся данные текущего запуска." />
        </div>
      </section>
    );
  }

  const isSuccess = lastRun.status === "success";
  const duration = lastRun.durationMs < 1000 ? "< 1 сек" : `${(lastRun.durationMs / 1000).toFixed(1)} сек`;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className={classNames("grid size-10 place-items-center rounded-xl", isSuccess ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-600")}>
            {isSuccess ? <CheckCircle2 size={20} /> : <XCircle size={20} />}
          </span>
          <div><h2 className="text-base font-semibold text-slate-950">Последний запуск</h2><p className="mt-1 text-sm text-slate-500">{lastRun.generatedAt}</p></div>
        </div>
        <span className={classNames("rounded-full px-2.5 py-1 text-xs font-semibold", isSuccess ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")}>
          {isSuccess ? "Успешно" : "Ошибка"}
        </span>
      </div>
      <dl className="mt-5 grid grid-cols-3 divide-x divide-slate-100 border-y border-slate-100 py-4 text-center">
        <div><dt className="text-[11px] text-slate-400">Длительность</dt><dd className="mt-1 text-sm font-semibold text-slate-800">{duration}</dd></div>
        <div><dt className="text-[11px] text-slate-400">Сигналов</dt><dd className="mt-1 text-sm font-semibold text-slate-800">{lastRun.signalCount}</dd></div>
        <div><dt className="text-[11px] text-slate-400">Карточек</dt><dd className="mt-1 text-sm font-semibold text-slate-800">{lastRun.decisionCardCount}</dd></div>
      </dl>
    </section>
  );
}

function DashboardPage({
  data,
  onNavigate,
  onGenerate,
  isGenerating,
  lastGeneratedAt,
  lastRun,
  onRefreshWidget,
  refreshingWidget,
}: {
  data: DashboardData;
  onNavigate: (page: NavigationPage) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  lastGeneratedAt: string | null;
  lastRun: LastRun | null;
  onRefreshWidget: (widget: WidgetName) => void;
  refreshingWidget: WidgetName | null;
}) {
  const topOpportunities = data.signals.filter((signal) => signal.type === "opportunity").slice(0, 3);
  const topRisks = data.signals.filter((signal) => signal.type === "risk").slice(0, 3);

  return (
    <>
      <PageIntro eyebrow="Revenue Engine" title="Доброе утро, Алексей">
        Фокус на день: деньги, критичные сроки и действия, которые можно выполнить сейчас.
      </PageIntro>
      <ActivityMetrics data={data} />
      <div className="mt-5"><KPICards data={data} /></div>
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.8fr)]">
        <RecentSignals data={data} onNavigate={onNavigate} onRefresh={() => onRefreshWidget("signals")} isRefreshing={refreshingWidget === "signals"} />
        <div className="space-y-5">
          <PriorityList title="Топ возможностей" subtitle="Быстрый путь к дополнительной выручке." items={topOpportunities} onNavigate={onNavigate} onRefresh={() => onRefreshWidget("opportunities")} isRefreshing={refreshingWidget === "opportunities"} />
          <PriorityList title="Топ рисков" subtitle="Не потеряйте деньги из-за задержки." items={topRisks} isRisk onNavigate={onNavigate} onRefresh={() => onRefreshWidget("opportunities")} isRefreshing={refreshingWidget === "opportunities"} />
        </div>
      </div>
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.8fr)]">
        <MorningBriefCard data={data} onNavigate={onNavigate} onGenerate={onGenerate} isGenerating={isGenerating} lastGeneratedAt={lastGeneratedAt} onRefresh={() => onRefreshWidget("morningBrief")} />
        <div className="space-y-5">
          <SourceStatus data={data} onNavigate={onNavigate} onRefresh={() => onRefreshWidget("sources")} isRefreshing={refreshingWidget === "sources"} />
          <LastRunCard lastRun={lastRun} />
        </div>
      </div>
    </>
  );
}

function SignalsPage({ data }: { data: DashboardData }) {
  return (
    <>
      <PageIntro eyebrow="Revenue engine" title="Сигналы">
        Входящие изменения из внутренних и внешних источников. Показываем только те, что влияют на деньги, сроки или риск.
      </PageIntro>
      <section className="rounded-2xl border border-slate-200 bg-white shadow-card">
        <div className="flex flex-col gap-3 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-500">{data.signals.length} сигналов в текущем потоке</p>
          <div className="flex flex-wrap gap-2">
            {["Все", "Возможности", "Риски", "Рынок"].map((label, index) => <span key={label} className={classNames("rounded-full px-3 py-1.5 text-xs font-semibold", index === 0 ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600")}>{label}</span>)}
          </div>
        </div>
        <div className="p-5 sm:p-6">
          {data.signals.length > 0 ? (
            data.signals.map((signal) => <SignalRow key={signal.id} signal={signal} onOpen={() => undefined} />)
          ) : (
            <p className="text-sm text-slate-500">Сигналы ещё не поступили из backend.</p>
          )}
        </div>
      </section>
    </>
  );
}

function DecisionCardsPage({ data }: { data: DashboardData }) {
  return (
    <>
      <PageIntro eyebrow="Action layer" title="Карточки решений">
        Каждая карточка связывает сигнал с понятным действием, сроком и ожидаемым финансовым эффектом.
      </PageIntro>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        {data.decisionCards.map((card) => (
          <article key={card.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-card">
            <div className="flex items-start justify-between gap-3">
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{card.category}</span>
              <span className={classNames("text-sm font-bold", card.impact.startsWith("-") ? "text-rose-600" : "text-emerald-600")}>{card.impact}</span>
            </div>
            <h2 className="mt-4 text-lg font-semibold tracking-tight text-slate-950">{card.title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">{card.summary}</p>
            <dl className="mt-5 grid grid-cols-3 gap-2 border-y border-slate-100 py-4 text-center">
              <div><dt className="text-[11px] text-slate-400">Уверенность</dt><dd className="mt-1 text-sm font-semibold text-slate-800">{card.confidence}</dd></div>
              <div><dt className="text-[11px] text-slate-400">Горизонт</dt><dd className="mt-1 text-sm font-semibold text-slate-800">{card.horizon}</dd></div>
              <div><dt className="text-[11px] text-slate-400">Владелец</dt><dd className="mt-1 truncate text-sm font-semibold text-slate-800">{card.owner}</dd></div>
            </dl>
            <ol className="mt-5 space-y-3">
              {card.steps.map((step, index) => <li key={step} className="flex gap-3 text-sm leading-5 text-slate-600"><span className="grid size-5 shrink-0 place-items-center rounded-full bg-emerald-50 text-xs font-bold text-emerald-700">{index + 1}</span>{step}</li>)}
            </ol>
            <button className="mt-6 min-h-11 rounded-xl bg-slate-950 px-4 text-sm font-semibold text-white hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2">Взять в работу</button>
          </article>
        ))}
      </div>
    </>
  );
}

function MorningBriefPage({ data }: { data: DashboardData }) {
  const brief = data.morningBrief;
  return (
    <>
      <PageIntro eyebrow={brief.generatedAt} title={brief.title}>
        {brief.summary}
      </PageIntro>
      <section className="rounded-2xl bg-slate-950 p-5 text-white shadow-card sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300">Главное действие на сегодня</p>
        <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div><h2 className="text-2xl font-semibold tracking-tight">{brief.mainAction.title}</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">{brief.mainAction.description}</p></div>
          <div className="rounded-xl bg-white/10 px-4 py-3 text-right"><p className="text-xs text-slate-300">Потенциал</p><p className="mt-1 text-xl font-bold text-emerald-300">{brief.mainAction.effect}</p></div>
        </div>
      </section>
      <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6"><h2 className="text-base font-semibold text-slate-950">Возможности</h2><div className="mt-4 space-y-3">{brief.opportunities.map((item) => <BriefItem key={item.id} title={item.title} effect={item.effect} deadline={item.deadline} description={item.description} kind={item.kind} />)}</div></section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6"><h2 className="text-base font-semibold text-slate-950">Риски</h2><div className="mt-4 space-y-3">{brief.risks.map((item) => <BriefItem key={item.id} title={item.title} effect={item.effect} deadline={item.deadline} description={item.description} kind={item.kind} />)}</div></section>
      </div>
      <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6"><h2 className="text-base font-semibold text-slate-950">Что происходит на рынке</h2><ul className="mt-4 grid gap-3 md:grid-cols-3">{brief.marketNotes.map((note) => <li key={note} className="rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">{note}</li>)}</ul></section>
    </>
  );
}

function BriefItem({ title, effect, deadline, description, kind }: { title: string; effect: string; deadline: string; description: string; kind: "opportunity" | "risk" }) {
  const risk = kind === "risk";
  return <article className="rounded-xl border border-slate-100 p-4"><div className="flex items-start justify-between gap-3"><h3 className="font-semibold text-slate-900">{title}</h3><span className={classNames("text-sm font-bold", risk ? "text-rose-600" : "text-emerald-600")}>{effect}</span></div><p className="mt-2 text-sm leading-5 text-slate-500">{description}</p><p className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-slate-500"><Clock3 size={13} /> {deadline}</p></article>;
}

function SourcesPage({ data }: { data: DashboardData }) {
  return (
    <>
      <PageIntro eyebrow="Data quality" title="Источники">
        Backend пока не предоставляет endpoint статусов источников. Здесь появятся данные после его добавления без изменения интерфейса.
      </PageIntro>
      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
        <div className="hidden grid-cols-[minmax(220px,1.3fr)_1fr_1fr_1fr] gap-4 border-b border-slate-100 bg-slate-50 px-6 py-3 text-xs font-semibold uppercase tracking-wide text-slate-400 md:grid"><span>Источник</span><span>Статус</span><span>Последняя синхронизация</span><span>Комментарий</span></div>
        {data.sources.length > 0 ? data.sources.map((source) => <article key={source.id} className="grid gap-3 border-b border-slate-100 px-5 py-5 last:border-0 md:grid-cols-[minmax(220px,1.3fr)_1fr_1fr_1fr] md:items-center md:gap-4 md:px-6"><div><h2 className="font-semibold text-slate-900">{source.name}</h2><p className="mt-1 text-xs text-slate-500">{source.type}</p></div><div><span className={classNames("inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-semibold", source.status === "online" ? "bg-emerald-50 text-emerald-700" : source.status === "warning" ? "bg-amber-50 text-amber-700" : "bg-rose-50 text-rose-700")}><span className={classNames("size-1.5 rounded-full", source.status === "online" ? "bg-emerald-500" : source.status === "warning" ? "bg-amber-500" : "bg-rose-500")} />{source.freshness}</span></div><p className="text-sm text-slate-600">{source.lastSync}</p><p className="text-sm leading-5 text-slate-500">{source.notes}</p></article>) : <p className="px-5 py-8 text-sm text-slate-500">Статусы источников пока не доступны через backend API.</p>}
      </section>
    </>
  );
}

function SettingsPage({ data }: { data: DashboardData }) {
  return (
    <>
      <PageIntro eyebrow="Configuration" title="Настройки">
        Интерфейс подключён к FastAPI. Базовый URL API задаётся переменной окружения VITE_API_URL.
      </PageIntro>
      <div className="space-y-5">
        {data.settings.map((section) => <section key={section.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6"><h2 className="text-lg font-semibold text-slate-950">{section.title}</h2><p className="mt-1 text-sm text-slate-500">{section.description}</p><div className="mt-5 divide-y divide-slate-100">{section.items.map((item) => <div key={item.id} className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-8"><div><h3 className="text-sm font-semibold text-slate-800">{item.label}</h3><p className="mt-1 text-xs leading-5 text-slate-500">{item.hint}</p></div><code className="w-fit rounded-lg bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">{item.value}</code></div>)}</div></section>)}
      </div>
    </>
  );
}

function App() {
  const [activePage, setActivePage] = useState<NavigationPage>("dashboard");
  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGeneratingBrief, setIsGeneratingBrief] = useState(false);
  const [refreshingWidget, setRefreshingWidget] = useState<WidgetName | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastGeneratedAt, setLastGeneratedAt] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<LastRun | null>(null);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const dismissToast = (id: number) => setToasts((current) => current.filter((toast) => toast.id !== id));
  const showToast = (toast: Omit<ToastMessage, "id">) => {
    const id = Date.now();
    setToasts((current) => [...current, { ...toast, id }]);
    window.setTimeout(() => dismissToast(id), 6000);
  };

  const refreshData = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setData(await getDashboardData());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Не удалось загрузить данные.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void refreshData();
  }, []);

  const refreshWidget = async (widget: WidgetName) => {
    setRefreshingWidget(widget);
    try {
      setData(await getDashboardData());
    } catch (error) {
      showToast({ kind: "error", title: "Не удалось обновить виджет", description: error instanceof Error ? error.message : "Повторите попытку позже." });
    } finally {
      setRefreshingWidget(null);
    }
  };

  const generateMorningBrief = async () => {
    const startedAt = performance.now();
    setIsGeneratingBrief(true);

    try {
      const dashboardData = await generateMorningBriefDashboardData();
      setData(dashboardData);
      setLastGeneratedAt(dashboardData.morningBrief.generatedAt);
      setLastRun({
        generatedAt: dashboardData.morningBrief.generatedAt,
        status: "success",
        durationMs: performance.now() - startedAt,
        signalCount: dashboardData.signals.length,
        decisionCardCount: dashboardData.decisionCards.length,
      });
      showToast({ kind: "success", title: "Morning Brief успешно сформирован" });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Повторите попытку позже.";
      setLastRun({
        generatedAt: new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date()),
        status: "error",
        durationMs: performance.now() - startedAt,
        signalCount: data?.signals.length ?? 0,
        decisionCardCount: 0,
      });
      showToast({ kind: "error", title: "Не удалось сформировать Morning Brief", description: message });
    } finally {
      setIsGeneratingBrief(false);
    }
  };

  const page = (() => {
    if (!data) {
      return null;
    }

    const dashboardData: DashboardData = data;
    const pageProps = { data: dashboardData, onNavigate: setActivePage };

    return {
      dashboard: (
        <DashboardPage
          {...pageProps}
          onGenerate={generateMorningBrief}
          isGenerating={isGeneratingBrief}
          lastGeneratedAt={lastGeneratedAt}
          lastRun={lastRun}
          onRefreshWidget={refreshWidget}
          refreshingWidget={refreshingWidget}
        />
      ),
      signals: <SignalsPage data={dashboardData} />,
      "decision-cards": <DecisionCardsPage data={dashboardData} />,
      "morning-brief": <MorningBriefPage data={dashboardData} />,
      sources: <SourcesPage data={dashboardData} />,
      settings: <SettingsPage data={dashboardData} />,
    }[activePage];
  })();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <Sidebar activePage={activePage} isOpen={mobileNavigationOpen} onNavigate={setActivePage} onClose={() => setMobileNavigationOpen(false)} />
      <div className="min-h-screen lg:pl-[272px]">
        <Header activePage={activePage} onMenuClick={() => setMobileNavigationOpen(true)} onRefresh={refreshData} isLoading={isLoading} />
        <main className="px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
          {loadError ? <div role="alert" className="mb-6 flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><AlertTriangle className="mt-0.5 shrink-0" size={18} /><div><p className="font-semibold">Не удалось обновить dashboard</p><p className="mt-1">{loadError}</p></div></div> : null}
          {page ?? (
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card" aria-live="polite">
              <p className="font-semibold text-slate-900">{isLoading ? "Загружаем данные из backend…" : "Данные пока недоступны"}</p>
              <p className="mt-2 text-sm text-slate-500">
                {isLoading ? "Пожалуйста, подождите." : "Проверьте подключение к FastAPI и повторите загрузку."}
              </p>
            </section>
          )}
        </main>
      </div>
      <ToastViewport toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default App;