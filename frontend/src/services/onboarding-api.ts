import { apiClient } from "./api-client";

/** Публичный результат CS12 onboarding provisioning. */
export interface OnboardingResponse {
  app_user_id: string;
  agency_id: string;
  role: string;
  replayed: boolean;
}

/**
 * Первичный onboarding authenticated Clerk user.
 *
 * Backend идемпотентен: 201 — первое создание tenant-цепочки,
 * 200 — replay для уже существующего пользователя. Оба статуса — успех.
 * Bearer добавляется централизованно в ApiClient; body у запроса нет.
 */
export function requestOnboarding(): Promise<OnboardingResponse> {
  return apiClient.post<OnboardingResponse>("/onboarding");
}
