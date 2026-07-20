/** Take capture on mobile: suggestions to tap and bend, skip always there. */

import { useEffect, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { api, type Briefing } from "@/lib/api";
import { color } from "@/lib/tokens";

interface KeepRow {
  feed_item_id: string;
  briefing: Briefing;
  take: { id: string; text: string } | null;
}

export default function DarkroomScreen() {
  const [keeps, setKeeps] = useState<KeepRow[]>([]);
  const [index, setIndex] = useState(0);
  const [suggestions, setSuggestions] = useState<Array<{ stance: string; text: string }>>([]);
  const [text, setText] = useState("");
  const [startedFrom, setStartedFrom] = useState("");
  const [stance, setStance] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api.keeps().then((r) => setKeeps(r.keeps));
  }, []);

  const keep = keeps[index];

  useEffect(() => {
    if (!keep) return;
    setText(keep.take?.text ?? "");
    setStartedFrom("");
    setStance("");
    setSuggestions([]);
    void api.suggest(keep.briefing.id).then((r) => setSuggestions(r.suggestions));
  }, [keep]);

  if (!keep) {
    return (
      <View style={styles.centre}>
        <Text style={styles.display}>
          {keeps.length ? `${keeps.length} takes on the record.` : "Nothing kept yet."}
        </Text>
        <Text style={styles.dim}>
          {keeps.length
            ? "The machine is making your prints — pick them on the web contact sheet."
            : "Swipe right on the wire and the keepers land here."}
        </Text>
      </View>
    );
  }

  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api.createTake({
        briefing_id: keep.briefing.id,
        feed_item_id: keep.feed_item_id,
        text: text.trim(),
        suggested_text: startedFrom,
        stance,
      });
      setIndex((i) => i + 1);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView style={styles.root} contentContainerStyle={{ padding: 20, paddingTop: 64 }}>
      <View style={styles.headerRow}>
        <Text style={styles.wire}>
          TAKE {index + 1} OF {keeps.length}
        </Text>
        <Pressable onPress={() => setIndex((i) => i + 1)}>
          <Text style={styles.wire}>SKIP →</Text>
        </Pressable>
      </View>

      <View style={styles.print}>
        <Text style={styles.headline}>{keep.briefing.headline}</Text>
        <Text style={styles.body}>{keep.briefing.body}</Text>
      </View>

      {suggestions.map((s) => (
        <Pressable
          key={s.stance + s.text.slice(0, 10)}
          style={styles.suggestion}
          onPress={() => {
            setText(s.text);
            setStartedFrom(s.text);
            setStance(s.stance);
          }}
        >
          <Text style={styles.stance}>{s.stance}</Text>
          <Text style={styles.suggestionText}>{s.text}</Text>
        </Pressable>
      ))}

      <TextInput
        style={styles.editor}
        multiline
        value={text}
        onChangeText={setText}
        placeholder="One or two sharp sentences…"
        placeholderTextColor="rgba(218,213,201,0.35)"
      />

      <Pressable
        style={[styles.cta, (!text.trim() || busy) && { opacity: 0.4 }]}
        disabled={!text.trim() || busy}
        onPress={() => void submit()}
      >
        <Text style={styles.ctaText}>{busy ? "Developing…" : "Develop the prints"}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.graphite },
  centre: {
    flex: 1,
    backgroundColor: color.graphite,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 24,
  },
  headerRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: 14 },
  wire: { fontSize: 10, letterSpacing: 1, color: "rgba(218,213,201,0.5)" },
  print: {
    backgroundColor: color.silver,
    borderRadius: 3,
    padding: 20,
    marginBottom: 16,
  },
  headline: { fontSize: 21, lineHeight: 28, color: color.ink, fontWeight: "600" },
  body: { marginTop: 10, fontSize: 15, lineHeight: 23, color: "#3A4048" },
  suggestion: {
    backgroundColor: color.selenium,
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
  },
  stance: { fontSize: 10, letterSpacing: 1, color: color.fixerHot, marginBottom: 6 },
  suggestionText: { fontSize: 14, lineHeight: 21, color: "rgba(218,213,201,0.75)" },
  editor: {
    backgroundColor: color.selenium,
    borderRadius: 10,
    padding: 16,
    minHeight: 110,
    color: color.silver,
    fontSize: 16,
    lineHeight: 24,
    textAlignVertical: "top",
    marginTop: 6,
  },
  cta: {
    backgroundColor: color.safelight,
    borderRadius: 10,
    paddingVertical: 16,
    alignItems: "center",
    marginTop: 16,
    marginBottom: 60,
  },
  ctaText: { color: color.ink, fontWeight: "700", fontSize: 16 },
  display: { fontSize: 26, color: color.silver, textAlign: "center" },
  dim: { fontSize: 14, color: "rgba(218,213,201,0.55)", textAlign: "center" },
});
