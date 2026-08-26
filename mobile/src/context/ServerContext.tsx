import AsyncStorage from "@react-native-async-storage/async-storage";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { ApiError, getStatus } from "../api/client";
import { SystemStatus } from "../api/types";

const STORAGE_KEY = "pulso_base_url";
const DEFAULT_BASE_URL = "http://192.168.0.10:8000";
const POLL_INTERVAL_MS = 2000;

type ServerContextValue = {
  baseUrl: string;
  isBaseUrlLoaded: boolean;
  setBaseUrl: (url: string) => Promise<void>;
  status: SystemStatus | null;
  statusError: string | null;
  isReachable: boolean;
  refreshStatus: () => Promise<void>;
};

const ServerContext = createContext<ServerContextValue | undefined>(undefined);

export function ServerProvider({ children }: { children: React.ReactNode }) {
  const [baseUrl, setBaseUrlState] = useState(DEFAULT_BASE_URL);
  const [isBaseUrlLoaded, setIsBaseUrlLoaded] = useState(false);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [isReachable, setIsReachable] = useState(false);

  const baseUrlRef = useRef(baseUrl);
  baseUrlRef.current = baseUrl;

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      if (saved) setBaseUrlState(saved);
      setIsBaseUrlLoaded(true);
    });
  }, []);

  const setBaseUrl = useCallback(async (url: string) => {
    setBaseUrlState(url);
    await AsyncStorage.setItem(STORAGE_KEY, url);
  }, []);

  const refreshStatus = useCallback(async () => {
    if (!baseUrlRef.current) return;
    try {
      const data = await getStatus(baseUrlRef.current);
      setStatus(data);
      setStatusError(null);
      setIsReachable(true);
    } catch (err) {
      setIsReachable(false);
      setStatusError(err instanceof ApiError ? err.message : "Error desconocido");
    }
  }, []);

  useEffect(() => {
    if (!isBaseUrlLoaded) return;
    refreshStatus();
    const interval = setInterval(refreshStatus, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isBaseUrlLoaded, baseUrl, refreshStatus]);

  return (
    <ServerContext.Provider
      value={{
        baseUrl,
        isBaseUrlLoaded,
        setBaseUrl,
        status,
        statusError,
        isReachable,
        refreshStatus,
      }}
    >
      {children}
    </ServerContext.Provider>
  );
}

export function useServer(): ServerContextValue {
  const ctx = useContext(ServerContext);
  if (!ctx) throw new Error("useServer debe usarse dentro de <ServerProvider>");
  return ctx;
}
