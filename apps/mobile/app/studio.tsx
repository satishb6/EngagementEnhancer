import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { setToken } from "@/lib/api";
import { color } from "@/lib/tokens";

export default function StudioScreen() {
  const router = useRouter();
  return (
    <View style={styles.root}>
      <Text style={styles.wire}>THE CONTROLS</Text>
      <Text style={styles.display}>Studio</Text>
      <Text style={styles.dim}>
        Protocols, modes, BYOK keys, and learning resets live in the web
        Studio. This app is for the two things a phone is best at: the swipe
        and the take.
      </Text>
      <Pressable
        style={styles.cta}
        onPress={() => {
          void setToken(null).then(() => router.replace("/signin"));
        }}
      >
        <Text style={styles.ctaText}>Sign out</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: color.graphite,
    padding: 28,
    paddingTop: 90,
    gap: 10,
  },
  wire: { fontSize: 10, letterSpacing: 1.2, color: "rgba(218,213,201,0.45)" },
  display: { fontSize: 32, color: color.silver },
  dim: { fontSize: 14, lineHeight: 21, color: "rgba(218,213,201,0.55)" },
  cta: {
    backgroundColor: color.selenium,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 24,
  },
  ctaText: { color: color.spike, fontWeight: "600" },
});
