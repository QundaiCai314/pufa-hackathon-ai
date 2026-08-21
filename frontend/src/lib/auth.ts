/**
 * 认证工具
 * 统一管理登录态
 */

const AUTH_KEY = 'qingpu_auth';

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  user_type?: string;
}

export interface AuthState {
  token: string;
  user: AuthUser;
}

export function getAuth(): AuthState | null {
  try {
    return JSON.parse(localStorage.getItem(AUTH_KEY) || 'null');
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return getAuth()?.token || null;
}

export function getUser(): AuthUser | null {
  return getAuth()?.user || null;
}

export function isAdmin(): boolean {
  const user = getUser();
  return !!user?.is_admin || user?.user_type === 'admin';
}

export function setAuth(data: AuthState): void {
  localStorage.setItem(AUTH_KEY, JSON.stringify(data));
}

export function clearAuth(): void {
  localStorage.removeItem(AUTH_KEY);
}

export function getAuthHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}