import React, { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";

import { getPolicies } from "../../src/api/client";
import { PolicySummary } from "../../src/api/types";
import { PolicyListItem } from "../../src/components/PolicyListItem";
import { TopBar } from "../../src/components/TopBar";
import { useServer } from "../../src/context/ServerContext";
import { useAppTheme } from "../../src/theme/ThemeProvider";

export default function PatternsScreen() {
  const { colors } = useAppTheme();
  const { baseUrl, isBaseUrlLoaded } = useServer();

  const [policies, setPolicies] = useState<PolicySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!baseUrl) return;
    setLoading(true);
    setError(null);
    try {
      setPolicies(await getPolicies(baseUrl));
    } catch (err: any) {
      setError(err?.message ?? "No se pudieron cargar las políticas.");
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    if (isBaseUrlLoaded) load();
  }, [isBaseUrlLoaded, load]);

  return (
    <View style={[styles.screen, { backgroundColor: colors.background }]}>
      <TopBar />
      <FlatList
        data={policies}
        keyExtractor={(item) => item.code}
        contentContainerStyle={styles.content}
        renderItem={({ item }) => <PolicyListItem policy={item} />}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={load} tintColor={colors.primary} />
        }
        ListHeaderComponent={
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            Elegí una política para editar sus 6 motores
          </Text>
        }
        ListEmptyComponent={
          error ? (
            <Text style={[styles.error, { color: colors.danger }]}>{error}</Text>
          ) : null
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 16, paddingBottom: 40 },
  title: {
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 14,
  },
  error: {
    fontSize: 13,
  },
});
