import { invoke } from '@tauri-apps/api/core';

import { apiBaseUrl, isDesktop } from './desktop';

export interface SavedLogin {
  email: string;
  password: string;
}

export const loadSavedLogin = () => isDesktop
  ? invoke<SavedLogin | null>('load_saved_login', { server: apiBaseUrl() })
  : Promise.resolve(null);

export const saveLogin = (login: SavedLogin) => invoke<void>('save_login', {
  server: apiBaseUrl(), ...login,
});

export const clearSavedLogin = () => invoke<void>('clear_saved_login', { server: apiBaseUrl() });
