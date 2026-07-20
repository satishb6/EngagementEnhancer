import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
} from "react-native";
import { api, setToken } from "@/lib/api";
import { color } from "@/lib/tokens";

export default function SignInScreen() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");

  const submit = async () => {
    setError("");
    try {
      const res =
        mode === "login"
          ? await api.login(email, password)
          : await api.signup(email, password);
      await setToken(res.token);
      router.replace("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something broke. Try again.");
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <Text style={styles.wire}>THE WIRE IS LIVE</Text>
      <Text style={styles.display}>{mode === "login" ? "Sign in" : "Start your wire"}</Text>
      <TextInput
        style={styles.input}
        value={email}
        onChangeText={setEmail}
        placeholder="email"
        placeholderTextColor="rgba(218,213,201,0.35)"
        autoCapitalize="none"
        keyboardType="email-address"
      />
      <TextInput
        style={styles.input}
        value={password}
        onChangeText={setPassword}
        placeholder="password"
        placeholderTextColor="rgba(218,213,201,0.35)"
        secureTextEntry
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable style={styles.cta} onPress={() => void submit()}>
        <Text style={styles.ctaText}>{mode === "login" ? "Open the wire" : "Create account"}</Text>
      </Pressable>
      <Pressable onPress={() => setMode((m) => (m === "login" ? "signup" : "login"))}>
        <Text style={styles.switch}>
          {mode === "login" ? "New here? Start your wire" : "Already wired? Sign in"}
        </Text>
      </Pressable>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: color.graphite,
    justifyContent: "center",
    padding: 28,
    gap: 12,
  },
  wire: { fontSize: 10, letterSpacing: 1.2, color: "rgba(218,213,201,0.45)" },
  display: { fontSize: 32, color: color.silver, marginBottom: 16 },
  input: {
    backgroundColor: color.selenium,
    borderRadius: 10,
    paddingHorizontal: 18,
    paddingVertical: 14,
    color: color.silver,
    fontSize: 16,
  },
  error: { color: color.spike, fontSize: 13 },
  cta: {
    backgroundColor: color.safelight,
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: "center",
    marginTop: 8,
  },
  ctaText: { color: color.ink, fontWeight: "700", fontSize: 16 },
  switch: { color: color.safelight, textAlign: "center", marginTop: 14, fontSize: 14 },
});
