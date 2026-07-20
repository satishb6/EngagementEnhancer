"use client";

/**
 * THE LATTICE — the 3D knowledge graph.
 *
 * Positions come from the server's cached projection of real briefing
 * embeddings (never random). InstancedMesh for nodes, one merged
 * BufferGeometry for edges. Exposure semantics: unexposed nodes sit dim and
 * cool in fixer; nodes you wrote a take on are exposed — brighter, warmer,
 * safelight. Timeline scrub replays growth from day one. Reduced-motion
 * falls back to a static 2D projection with the same colour semantics.
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Billboard, Text } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { api, type Graph } from "@/lib/api";
import { Print, Wire } from "@/components/ui/primitives";

const FIXER = new THREE.Color("#6D64A3");
const FIXER_HOT = new THREE.Color("#9A8EE0");
const SAFELIGHT = new THREE.Color("#FF8A3D");

export function Lattice() {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [search, setSearch] = useState("");
  const [timeline, setTimeline] = useState(1); // 0 = day one, 1 = today
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    void api.graph().then(setGraph);
  }, []);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    void api.graphNode(selected).then((d) => setDetail(d));
  }, [selected]);

  const timestamps = useMemo(() => {
    if (!graph?.nodes.length) return { min: 0, max: 1 };
    const times = graph.nodes.map((n) => Date.parse(n.created_at));
    return { min: Math.min(...times), max: Math.max(...times) };
  }, [graph]);

  const cutoff =
    timestamps.min + (timestamps.max - timestamps.min) * timeline + 1;

  const visible = useMemo(
    () =>
      (graph?.nodes ?? []).filter(
        (n) => n.position && Date.parse(n.created_at) <= cutoff,
      ),
    [graph, cutoff],
  );
  const matches = useMemo(() => {
    if (!search.trim()) return null;
    const q = search.toLowerCase();
    return new Set(
      visible
        .filter(
          (n) =>
            n.headline.toLowerCase().includes(q) ||
            n.region.toLowerCase().includes(q),
        )
        .map((n) => n.id),
    );
  }, [search, visible]);

  if (!graph) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Wire tone="machine">exposing the lattice…</Wire>
      </div>
    );
  }

  const exposed = visible.filter((n) => n.has_take).length;

  return (
    <div className="relative h-[calc(100vh-104px)]">
      {reduced ? (
        <Flat2DLattice
          graph={graph}
          visible={visible}
          matches={matches}
          onSelect={setSelected}
        />
      ) : (
        <Canvas camera={{ position: [0, 0, 46], fov: 55 }} dpr={[1, 2]}>
          <color attach="background" args={["#0E1116"]} />
          <ambientLight intensity={0.35} />
          <pointLight position={[30, 30, 30]} intensity={220} color="#9A8EE0" />
          <pointLight position={[-30, -20, 10]} intensity={140} color="#FF8A3D" />
          <NodeCloud
            graph={graph}
            visible={visible}
            matches={matches}
            selected={selected}
            onSelect={setSelected}
          />
          <Edges graph={graph} visibleIds={new Set(visible.map((n) => n.id))} />
          <RegionLabels graph={graph} />
          <OrbitControls
            enableDamping
            dampingFactor={0.06}
            rotateSpeed={0.6}
            minDistance={12}
            maxDistance={120}
          />
        </Canvas>
      )}

      {/* HUD */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-6">
        <div>
          <Wire tone="dim">
            {visible.length} crystals · {exposed} exposed
          </Wire>
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="search the lattice"
          className="pointer-events-auto w-56 rounded-chrome bg-selenium/90 px-4 py-2 text-label text-silver outline-none placeholder:text-silver-dim/40"
        />
      </div>

      {/* timeline scrub — drag back and watch it grow from nothing */}
      <div className="absolute inset-x-0 bottom-0 flex items-center gap-4 p-6">
        <Wire tone="dim">day 1</Wire>
        <input
          type="range"
          min={0}
          max={1000}
          value={timeline * 1000}
          onChange={(e) => setTimeline(Number(e.target.value) / 1000)}
          className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-selenium accent-[#FF8A3D]"
        />
        <Wire tone={timeline > 0.99 ? "human" : "dim"}>
          {timeline > 0.99 ? "today" : "scrubbing"}
        </Wire>
      </div>

      {/* Print panel for the selected node */}
      {selected && detail ? (
        <div className="absolute right-6 top-16 w-96 max-w-[calc(100vw-48px)]">
          <NodePanel detail={detail} onClose={() => setSelected(null)} />
        </div>
      ) : null}
    </div>
  );
}

function NodeCloud({
  graph,
  visible,
  matches,
  selected,
  onSelect,
}: {
  graph: Graph;
  visible: Graph["nodes"];
  matches: Set<string> | null;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const count = visible.length;

  const neighbourMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const e of graph.edges) {
      if (!map.has(e.source)) map.set(e.source, new Set());
      if (!map.has(e.target)) map.set(e.target, new Set());
      map.get(e.source)!.add(e.target);
      map.get(e.target)!.add(e.source);
    }
    return map;
  }, [graph.edges]);

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const dummy = new THREE.Object3D();
    const colour = new THREE.Color();
    const now = Date.now();
    const hoveredId = hovered !== null ? visible[hovered]?.id : null;
    const hoodIds = hoveredId ? neighbourMap.get(hoveredId) : null;

    visible.forEach((node, i) => {
      const [x, y, z] = node.position!;
      const size = 0.35 + Math.min(node.engagement, 12) * 0.09 + (node.has_take ? 0.18 : 0);
      dummy.position.set(x, y, z);
      dummy.scale.setScalar(size);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);

      // luminance by recency: old crystals darken, never vanish
      const ageDays = (now - Date.parse(node.created_at)) / 86400000;
      const lum = Math.max(0.35, 1 - ageDays / 30);
      colour.copy(node.has_take ? SAFELIGHT : node.id === selected ? FIXER_HOT : FIXER);
      colour.multiplyScalar(node.has_take ? lum : lum * 0.8);

      const dimmedByHover = hoveredId && node.id !== hoveredId && !hoodIds?.has(node.id);
      const dimmedBySearch = matches && !matches.has(node.id);
      if (dimmedByHover || dimmedBySearch) colour.multiplyScalar(0.15);
      if (matches?.has(node.id)) colour.copy(SAFELIGHT).multiplyScalar(1.2);
      mesh.setColorAt(i, colour);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [visible, hovered, matches, selected, neighbourMap]);

  return (
    <instancedMesh
      key={count}
      ref={meshRef}
      args={[undefined, undefined, Math.max(count, 1)]}
      onPointerMove={(e) => {
        e.stopPropagation();
        setHovered(e.instanceId ?? null);
      }}
      onPointerOut={() => setHovered(null)}
      onClick={(e) => {
        e.stopPropagation();
        if (e.instanceId !== undefined && visible[e.instanceId]) {
          onSelect(visible[e.instanceId].id);
        }
      }}
    >
      <sphereGeometry args={[1, 12, 12]} />
      <meshStandardMaterial
        roughness={0.35}
        metalness={0.15}
        emissive={"#1a1530"}
        emissiveIntensity={0.6}
      />
    </instancedMesh>
  );
}

function Edges({ graph, visibleIds }: { graph: Graph; visibleIds: Set<string> }) {
  const geometry = useMemo(() => {
    const positions: number[] = [];
    const colours: number[] = [];
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    for (const e of graph.edges) {
      const a = byId.get(e.source);
      const b = byId.get(e.target);
      if (!a?.position || !b?.position) continue;
      if (!visibleIds.has(a.id) || !visibleIds.has(b.id)) continue;
      positions.push(...a.position, ...b.position);
      const c = a.has_take && b.has_take ? SAFELIGHT : FIXER;
      const alpha = 0.15 + e.strength * 0.5;
      colours.push(c.r * alpha, c.g * alpha, c.b * alpha);
      colours.push(c.r * alpha, c.g * alpha, c.b * alpha);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(colours, 3));
    return geo;
  }, [graph, visibleIds]);

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial vertexColors transparent opacity={0.55} />
    </lineSegments>
  );
}

function RegionLabels({ graph }: { graph: Graph }) {
  const { camera } = useThree();
  const [zoomed, setZoomed] = useState(true);
  useFrame(() => {
    const dist = camera.position.length();
    const show = dist < 80;
    if (show !== zoomed) setZoomed(show);
  });
  if (!zoomed) return null;
  return (
    <>
      {graph.regions.map((r) => (
        <Billboard key={r.key} position={r.position as [number, number, number]}>
          <Text
            fontSize={1.15}
            letterSpacing={0.12}
            color={r.exposed > 0 ? "#FF8A3D" : "#B5AFA2"}
            anchorX="center"
            fillOpacity={0.85}
          >
            {`${r.key.toUpperCase()} · ${r.count}`}
          </Text>
        </Billboard>
      ))}
    </>
  );
}

/** Reduced-motion / low-power: same colour semantics, same tap targets. */
function Flat2DLattice({
  visible,
  matches,
  onSelect,
}: {
  graph: Graph;
  visible: Graph["nodes"];
  matches: Set<string> | null;
  onSelect: (id: string) => void;
}) {
  const extent = 30;
  return (
    <svg viewBox={`-${extent} -${extent} ${extent * 2} ${extent * 2}`} className="h-full w-full bg-[#0E1116]">
      {visible.map((n) => {
        const [x, y] = n.position!;
        const r = 0.5 + Math.min(n.engagement, 12) * 0.1;
        const dim = matches && !matches.has(n.id);
        return (
          <circle
            key={n.id}
            cx={x}
            cy={-y}
            r={r}
            fill={n.has_take ? "#FF8A3D" : "#6D64A3"}
            opacity={dim ? 0.15 : 0.9}
            onClick={() => onSelect(n.id)}
            style={{ cursor: "pointer" }}
          >
            <title>{n.headline}</title>
          </circle>
        );
      })}
    </svg>
  );
}

function NodePanel({
  detail,
  onClose,
}: {
  detail: Record<string, unknown>;
  onClose: () => void;
}) {
  const briefing = detail.briefing as
    | { headline: string; body: string; source_links: Array<{ domain: string; url: string }> }
    | undefined;
  const take = detail.take as { text: string; stance: string } | null | undefined;
  const pubs = (detail.publications as Array<{ status: string; engagement: Record<string, unknown> }>) ?? [];
  if (!briefing) return null;
  return (
    <Print className="max-h-[70vh] overflow-auto p-6" caption={take ? "EXPOSED · YOURS" : "UNEXPOSED"}>
      <div className="mb-2 flex justify-between">
        <Wire tone="machine">crystal</Wire>
        <button onClick={onClose}>
          <Wire tone="dim">close</Wire>
        </button>
      </div>
      <h3 className="font-display text-[20px] leading-snug text-ink">{briefing.headline}</h3>
      <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">{briefing.body}</p>
      {take ? (
        <div className="mt-4 border-l-2 border-safelight pl-3">
          <Wire tone="human">your take · {take.stance || "unlabelled"}</Wire>
          <p className="mt-1 text-[14px] text-ink">{take.text}</p>
        </div>
      ) : null}
      {pubs.length ? (
        <div className="mt-4">
          <Wire tone="machine">published</Wire>
          {pubs.map((p, i) => (
            <p key={i} className="mt-1 font-mono text-[12px] text-ink-soft">
              {p.status} · {JSON.stringify(p.engagement).slice(0, 60)}
            </p>
          ))}
        </div>
      ) : null}
    </Print>
  );
}
