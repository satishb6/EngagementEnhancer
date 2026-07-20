import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { color } from "@/lib/tokens";

export default function PrintsScreen() {
  return (
    <View style={styles.centre}>
      <Text style={styles.display}>Prints live on the big screen.</Text>
      <Text style={styles.dim}>
        The contact sheet, the Wire Room, and the Lattice want a desktop.
        Everything you make here is waiting there.
      </Text>
      <Pressable
        style={styles.cta}
        onPress={() => void Linking.openURL(process.env.EXPO_PUBLIC_WEB_URL ?? "http://localhost:3000")}
      >
        <Text style={styles.ctaText}>Open the web app</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  centre: {
    flex: 1,
    backgroundColor: color.graphite,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    padding: 28,
  },
  display: { fontSize: 26, color: color.silver, textAlign: "center" },
  dim: { fontSize: 14, lineHeight: 21, color: "rgba(218,213,201,0.55)", textAlign: "center" },
  cta: {
    backgroundColor: color.selenium,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 24,
    marginTop: 10,
  },
  ctaText: { color: color.silver, fontWeight: "600" },
});
