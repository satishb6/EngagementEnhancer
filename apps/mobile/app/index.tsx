/**
 * The Wire — the mobile swipe deck. Gesture Handler pan feeding Reanimated
 * shared values on the UI thread; the card tilts, edge glows map to drag
 * distance, release past threshold flies off with carried velocity.
 */

import { useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { api, getToken, type FeedItem } from "@/lib/api";
import { color, spring } from "@/lib/tokens";

const THRESHOLD = 120;

export default function WireScreen() {
  const router = useRouter();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const pending = useRef<Parameters<typeof api.swipe>[0]>([]);
  const shownAt = useRef(Date.now());

  useEffect(() => {
    void (async () => {
      if (!(await getToken())) {
        router.replace("/signin");
        return;
      }
      const res = await api.feed();
      setItems(res.items);
      setTotal(res.total_today || res.items.length);
    })();
  }, [router]);

  const flush = useCallback(async (force = false) => {
    if (pending.current.length >= 5 || (force && pending.current.length)) {
      const batch = pending.current.splice(0);
      try {
        await api.swipe(batch);
      } catch {
        pending.current.unshift(...batch);
      }
    }
  }, []);

  const onSwipe = useCallback(
    (direction: "left" | "right") => {
      setItems((current) => {
        const [top, ...rest] = current;
        if (!top) return current;
        pending.current.push({
          feed_item_id: top.feed_item_id,
          direction,
          dwell_ms: Date.now() - shownAt.current,
          client_event_id: `m-${top.feed_item_id.slice(0, 8)}-${Date.now()}`,
        });
        shownAt.current = Date.now();
        void flush();
        setDone((d) => d + 1);
        return rest;
      });
    },
    [flush],
  );

  useEffect(() => {
    const t = setInterval(() => void flush(true), 4000);
    return () => clearInterval(t);
  }, [flush]);

  if (!items.length) {
    return (
      <View style={styles.centre}>
        <Text style={styles.displayText}>The wire is clear.</Text>
        <Text style={styles.dimText}>
          {done ? `${done} sorted. Your keeps are in the Darkroom.` : "Refills as the day moves."}
        </Text>
      </View>
    );
  }

  const stack = items.slice(0, 3);
  return (
    <View style={styles.root}>
      <View style={styles.deck}>
        {stack
          .map((item, i) => (
            <DeckCard key={item.feed_item_id} item={item} depth={i} onSwipe={onSwipe} />
          ))
          .reverse()}
      </View>
      <View style={styles.footer}>
        <Pressable onPress={() => void api.undo().then(() => api.feed().then((r) => setItems(r.items)))}>
          <Text style={styles.wire}>UNDO</Text>
        </Pressable>
        <Text style={styles.wire}>
          {done} / {Math.max(total, done + items.length)}
        </Text>
        <Text style={styles.wire}>← TOSS · KEEP →</Text>
      </View>
    </View>
  );
}

function DeckCard({
  item,
  depth,
  onSwipe,
}: {
  item: FeedItem;
  depth: number;
  onSwipe: (d: "left" | "right") => void;
}) {
  const x = useSharedValue(0);
  const y = useSharedValue(0);
  const isTop = depth === 0;

  const pan = Gesture.Pan()
    .enabled(isTop)
    .onChange((e) => {
      x.value = e.translationX;
      y.value = e.translationY * 0.2;
    })
    .onEnd((e) => {
      if (Math.abs(x.value) > THRESHOLD || Math.abs(e.velocityX) > 800) {
        const dir = x.value > 0 ? "right" : "left";
        x.value = withTiming(Math.sign(x.value || e.velocityX) * 600, { duration: 220 });
        runOnJS(onSwipe)(dir);
      } else {
        x.value = withSpring(0, spring.settle);
        y.value = withSpring(0, spring.settle);
      }
    });

  const cardStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: x.value },
      { translateY: y.value + depth * 14 },
      { rotateZ: `${interpolate(x.value, [-300, 300], [-12, 12])}deg` },
      { scale: 1 - depth * 0.045 },
    ],
  }));

  const keepGlow = useAnimatedStyle(() => ({
    opacity: interpolate(x.value, [40, 200], [0, 1], "clamp"),
  }));
  const tossGlow = useAnimatedStyle(() => ({
    opacity: interpolate(x.value, [-200, -40], [1, 0], "clamp"),
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={[styles.card, cardStyle, { zIndex: 10 - depth }]}>
        <Animated.View style={[styles.edgeGlow, styles.edgeRight, keepGlow]} />
        <Animated.View style={[styles.edgeGlow, styles.edgeLeft, tossGlow]} />
        <Text style={styles.headline}>{item.briefing.headline}</Text>
        <Text style={styles.body} numberOfLines={8}>
          {item.briefing.body}
        </Text>
        <View style={styles.chips}>
          {item.briefing.source_links.slice(0, 3).map((s) => (
            <Text key={s.domain} style={styles.chip}>
              {s.domain.toUpperCase()}
            </Text>
          ))}
        </View>
        <Text style={styles.caption}>
          {(item.briefing.source_links.length || 1) + " SOURCES · CLUSTER " +
            item.briefing.cluster_id.slice(0, 4).toUpperCase()}
        </Text>
      </Animated.View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.graphite, paddingTop: 60 },
  centre: {
    flex: 1,
    backgroundColor: color.graphite,
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 24,
  },
  deck: { flex: 1, margin: 20 },
  card: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 40,
    backgroundColor: color.silver,
    borderRadius: 3,
    padding: 24,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 24 },
    shadowOpacity: 0.7,
    shadowRadius: 48,
    elevation: 18,
  },
  edgeGlow: { position: "absolute", top: 0, bottom: 0, width: 5 },
  edgeRight: { right: 0, backgroundColor: color.safelight, borderTopRightRadius: 3, borderBottomRightRadius: 3 },
  edgeLeft: { left: 0, backgroundColor: color.spike, borderTopLeftRadius: 3, borderBottomLeftRadius: 3 },
  headline: { fontSize: 22, lineHeight: 30, color: color.ink, fontWeight: "600" },
  body: { marginTop: 14, fontSize: 16, lineHeight: 25, color: "#3A4048", flex: 1 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 10 },
  chip: {
    fontSize: 10,
    letterSpacing: 0.8,
    color: "#6D64A3",
    borderWidth: 1,
    borderColor: "rgba(12,15,19,0.15)",
    borderRadius: 3,
    paddingHorizontal: 6,
    paddingVertical: 3,
  },
  caption: {
    fontSize: 9,
    letterSpacing: 1,
    color: "#6D64A3",
    borderTopWidth: 1,
    borderTopColor: "rgba(12,15,19,0.1)",
    paddingTop: 8,
  },
  footer: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 28,
    paddingBottom: 14,
  },
  wire: { fontSize: 10, letterSpacing: 1, color: "rgba(218,213,201,0.5)" },
  displayText: { fontSize: 28, color: color.silver },
  dimText: { fontSize: 15, color: "rgba(218,213,201,0.55)", textAlign: "center" },
});
