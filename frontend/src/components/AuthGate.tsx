import { useEffect, useState, type ReactNode } from "react";
import { SignIn, SignUp, useAuth } from "@clerk/react";
import { LoaderCircle } from "lucide-react";
import OnboardingGate from "./OnboardingGate";
import { setApiTokenProvider } from "../services/api-client";

// Приложение живёт на "/" без client-роутера, а Clerk-компоненты монтируются
// на выделенных путях (nginx уже отдаёт index.html через try_files для /sign-in и /sign-up).
const SIGN_IN_PATH = "/sign-in";
const SIGN_UP_PATH = "/sign-up";

/** Отслеживает текущий pathname: без роутера достаточно popstate-обновления. */
function useCurrentPath(): string {
  const [currentPath, setCurrentPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const handleLocationChange = () => setCurrentPath(window.location.pathname);

    window.addEventListener("popstate", handleLocationChange);
    return () => window.removeEventListener("popstate", handleLocationChange);
  }, []);

  return currentPath;
}

function AuthScreen({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      {children}
    </div>
  );
}

function AuthenticatingScreen() {
  return (
    <AuthScreen>
      <div className="flex flex-col items-center gap-3 text-slate-500">
        <LoaderCircle className="size-6 animate-spin" />
        <p className="text-sm font-medium">Проверяем сессию…</p>
      </div>
    </AuthScreen>
  );
}

/**
 * Auth-граница приложения: loading Clerk → SignIn/SignUp → onboarding → dashboard.
 *
 * Здесь же регистрируется единственный центральный источник токена для ApiClient:
 * страницы не получают token-параметры, JWT нигде не сохраняется и не логируется.
 */
export default function AuthGate() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const currentPath = useCurrentPath();

  useEffect(() => {
    setApiTokenProvider(() => getToken());
    return () => setApiTokenProvider(null);
  }, [getToken]);

  if (!isLoaded) {
    return <AuthenticatingScreen />;
  }

  if (isSignedIn) {
    return <OnboardingGate />;
  }

  if (currentPath === SIGN_UP_PATH || currentPath.startsWith(`${SIGN_UP_PATH}/`)) {
    return (
      <AuthScreen>
        <SignUp path={SIGN_UP_PATH} signInUrl={SIGN_IN_PATH} />
      </AuthScreen>
    );
  }

  return (
    <AuthScreen>
      <SignIn path={SIGN_IN_PATH} signUpUrl={SIGN_UP_PATH} />
    </AuthScreen>
  );
}
