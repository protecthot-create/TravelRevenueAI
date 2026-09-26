import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useAuth } from "@clerk/react";
import { AlertTriangle, LoaderCircle, LogOut, RefreshCw, ShieldAlert, type LucideIcon } from "lucide-react";
import DashboardApp from "../App";
import { ApiClientError } from "../services/api-client";
import { requestOnboarding, type OnboardingResponse } from "../services/onboarding-api";

type OnboardingState =
  | { kind: "loading" }
  | { kind: "onboarded"; data: OnboardingResponse }
  | { kind: "unauthorized" }
  | { kind: "inactive" }
  | { kind: "conflict" }
  | { kind: "failed"; hint: string };

function OnboardingCard({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-card sm:p-8">
        <div className="flex flex-col items-center text-center">
          <span className="grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-600">
            <Icon size={22} />
          </span>
          <h1 className="mt-4 text-lg font-semibold tracking-tight text-slate-950">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
        </div>
        {children ? <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">{children}</div> : null}
      </div>
    </div>
  );
}

function ActionButton({ onClick, variant = "primary", children }: { onClick: () => void; variant?: "primary" | "secondary"; children: ReactNode }) {
  const styles =
    variant === "primary"
      ? "bg-slate-950 text-white hover:bg-slate-800"
      : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50";
  return (
    <button
      onClick={onClick}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-5 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 ${styles}`}
    >
      {children}
    </button>
  );
}

/**
 * Onboarding-граница: выполняется после Clerk sign-in и перед DashboardApp.
 *
 * Backend идемпотентен (201 first / 200 replay), поэтому запрос выполняется заново
 * на каждую Clerk-сессию — backend является источником истины, клиентские
 * replay-флаги не используются. Onboarding-данные (agency_id и роль) живут только
 * в React state и передаются в DashboardApp пропом: persisted brief, history и
 * feedback контрактно требуют agency_id. При sign-out и смене сессии state
 * очищается вместе с размонтированием, а runId-гвард отсекает ответы от
 * устаревшей сессии.
 */
export default function OnboardingGate() {
  const { sessionId, signOut } = useAuth();
  const [state, setState] = useState<OnboardingState>({ kind: "loading" });
  const runIdRef = useRef(0);

  const runOnboarding = useCallback(async () => {
    const runId = ++runIdRef.current;
    setState({ kind: "loading" });

    try {
      const data = await requestOnboarding();
      if (runIdRef.current !== runId) {
        return;
      }
      setState({ kind: "onboarded", data });
    } catch (error) {
      if (runIdRef.current !== runId) {
        return;
      }
      if (error instanceof ApiClientError) {
        if (error.status === 401) {
          setState({ kind: "unauthorized" });
          return;
        }
        if (error.status === 403) {
          setState({ kind: "inactive" });
          return;
        }
        if (error.status === 409) {
          setState({ kind: "conflict" });
          return;
        }
        if (error.status === 0) {
          setState({ kind: "failed", hint: "Не удалось связаться с сервером. Проверьте подключение и повторите попытку." });
          return;
        }
      }
      setState({ kind: "failed", hint: "Не удалось подготовить рабочее пространство. Повторите попытку позже." });
    }
  }, []);

  useEffect(() => {
    void runOnboarding();
  }, [runOnboarding, sessionId]);

  if (state.kind === "onboarded") {
    return <DashboardApp agencyId={state.data.agency_id} />;
  }

  if (state.kind === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="flex flex-col items-center gap-3 text-slate-500">
          <LoaderCircle className="size-6 animate-spin" />
          <p className="text-sm font-medium">Подготавливаем рабочее пространство…</p>
        </div>
      </div>
    );
  }

  if (state.kind === "unauthorized") {
    return (
      <OnboardingCard icon={ShieldAlert} title="Требуется повторный вход" description="Сессия недействительна или истекла. Войдите заново, чтобы продолжить.">
        <ActionButton onClick={() => void signOut()}>
          <LogOut size={16} /> Войти заново
        </ActionButton>
      </OnboardingCard>
    );
  }

  if (state.kind === "inactive") {
    return (
      <OnboardingCard icon={ShieldAlert} title="Учётная запись неактивна" description="Доступ к рабочему пространству закрыт. Обратитесь к администратору.">
        <ActionButton onClick={() => void signOut()} variant="secondary">
          <LogOut size={16} /> Выйти
        </ActionButton>
      </OnboardingCard>
    );
  }

  if (state.kind === "conflict") {
    return (
      <OnboardingCard icon={AlertTriangle} title="Конфликт состояния аккаунта" description="Не удалось однозначно подготовить рабочее пространство. Попробуйте ещё раз или войдите заново.">
        <ActionButton onClick={() => void runOnboarding()}>
          <RefreshCw size={16} /> Повторить
        </ActionButton>
        <ActionButton onClick={() => void signOut()} variant="secondary">
          <LogOut size={16} /> Выйти
        </ActionButton>
      </OnboardingCard>
    );
  }

  return (
    <OnboardingCard icon={AlertTriangle} title="Что-то пошло не так" description={state.hint}>
      <ActionButton onClick={() => void runOnboarding()}>
        <RefreshCw size={16} /> Повторить
      </ActionButton>
      <ActionButton onClick={() => void signOut()} variant="secondary">
        <LogOut size={16} /> Выйти
      </ActionButton>
    </OnboardingCard>
  );
}
