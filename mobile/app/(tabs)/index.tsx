import React, { useCallback, useEffect, useState } from "react";
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { getPolicies, updateStatus } from "../../src/api/client";
import { PolicySummary } from "../../src/api/types";
import { GlobalIntensitySlider } from "../../src/components/GlobalIntensitySlider";
import { PolicyCard } from "../../src/components/PolicyCard";
import { StatusBanner } from "../../src/components/StatusBanner";
import { TopBar } from "../../src/components/TopBar";
import { useServer } from "../../src/context/ServerContext";
import { useAppTheme } from "../../src/theme/ThemeProvider";

export default function HomeScreen() {
  const { colors } = useAppTheme();
  const { baseUrl, isBaseUrlLoaded, status, refreshStatus } = useServer();

  const [policies, setPolicies] = useState<PolicySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPolicies = useCallback(async () => {
    if (!baseUrl) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getPolicies(baseUrl);
      setPolicies(data);
    } catch (err: any) {
      setError(err?.message ?? "No se pudieron cargar las políticas.");
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    if (isBaseUrlLoaded) loadPolicies();
  }, [isBaseUrlLoaded, loadPolicies]);

  const handleGlobalIntensityChange = async (value: number) => {
    try {
      await updateStatus(baseUrl, { global_intensity_percent: value });
      refreshStatus();
    } catch {
      // El próximo poll de estado va a reflejar el valor real igual.
    }
  };

  return (
    <View style={[styles.screen, { backgroundColor: colors.background }]}>
      <TopBar />
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={() => {
              loadPolicies();
              refreshStatus();
            }}
            tintColor={colors.primary}
          />
        }
      >
        <StatusBanner />

        <GlobalIntensitySlider
          value={status?.global_intensity_percent ?? 65}
          onChangeComplete={handleGlobalIntensityChange}
        />

        <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
          Patrones preconfigurados
        </Text>

        {error && (
          <Text style={[styles.error, { color: colors.danger }]}>{error}</Text>
        )}

        <View style={styles.grid}>
          {policies.map((policy) => (
            <PolicyCard key={policy.code} policy={policy} />
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.3,
    marginBottom: 12,
    textTransform: "uppercase",
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
  },
  error: {
    fontSize: 13,
    marginBottom: 12,
  },
});
