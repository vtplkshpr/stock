// Tidy-tree layout around the centre company, using each node's measured size.
//
// Three trees share the centre node as their root: "up" (information), "right" (suppliers) and
// "left" (customers). Each is laid out with d3-flextree, which packs nodes of different sizes
// without overlaps; the breadth axis is horizontal for "up" and vertical for the sides. If the
// information tree reaches down into a side tree, the information tree is lifted clear of it.
import { flextree, type FlexNode } from "d3-flextree";
import type { Dir, TNode } from "./store";

export interface Size { width: number; height: number }
export interface Box { x: number; y: number; width: number; height: number }

const DEPTH_GAP = { up: 64, side: 96 };
const SIBLING_GAP = 18;
const COUSIN_GAP = 40;

interface Item { id: string; width: number; height: number; children: Item[] }

export function layout(
  rootId: string,
  visible: TNode[],
  sizes: Map<string, Size>,
  childrenOf: (node: TNode) => string[],
): Map<string, Box> {
  const byId = new Map(visible.map((node) => [node.id, node]));
  const root = byId.get(rootId);
  const boxes = new Map<string, Box>();
  if (!root) return boxes;
  const centre = sizes.get(rootId) ?? { width: 280, height: 120 };
  boxes.set(rootId, { x: -centre.width / 2, y: -centre.height / 2, ...centre });

  const item = (id: string): Item => {
    const node = byId.get(id)!;
    const size = sizes.get(id) ?? { width: 160, height: 40 };
    return { id, ...size, children: childrenOf(node).filter((c) => byId.has(c)).map(item) };
  };

  const placeTree = (dir: Dir): Box[] => {
    const tops = childrenOf(root).filter((c) => byId.get(c)?.dir === dir);
    if (!tops.length) return [];
    const vertical = dir === "up";
    const rootItem: Item = { id: rootId, ...centre, children: tops.map(item) };
    const tree = flextree<Item>({
      nodeSize: (n) => {
        if (n.data.id === rootId) {
          return vertical ? [centre.width, centre.height / 2 + DEPTH_GAP.up]
                          : [centre.height, centre.width / 2 + DEPTH_GAP.side];
        }
        return vertical ? [n.data.width, n.data.height + DEPTH_GAP.up]
                        : [n.data.height, n.data.width + DEPTH_GAP.side];
      },
      spacing: (a, b) => (a.parent === b.parent ? SIBLING_GAP : COUSIN_GAP),
    });
    const hierarchy = tree.hierarchy(rootItem, (d) => d.children);
    tree(hierarchy);
    const shift = hierarchy.x;
    const placed: Box[] = [];
    hierarchy.each((n: FlexNode<Item>) => {
      if (n.data.id === rootId) return;
      const { width, height } = n.data;
      const breadth = n.x - shift;
      let box: Box;
      if (dir === "up") box = { x: breadth - width / 2, y: -n.y - height, width, height };
      else if (dir === "right") box = { x: n.y, y: breadth - height / 2, width, height };
      else box = { x: -n.y - width, y: breadth - height / 2, width, height };
      boxes.set(n.data.id, box);
      placed.push(box);
    });
    return placed;
  };

  const up = placeTree("up");
  const right = placeTree("right");
  const left = placeTree("left");

  // The information tree may reach into a side tree. Either lift the information tree above the
  // sides, or push the side trees outwards past it - whichever moves things less.
  const gap = COUSIN_GAP;
  const overlapX = (a: Box, b: Box) => a.x < b.x + b.width + gap && b.x < a.x + a.width + gap;
  const overlapY = (a: Box, b: Box) => a.y < b.y + b.height + gap && b.y < a.y + a.height + gap;
  let lift = 0;
  let pushRight = 0;
  let pushLeft = 0;
  for (const a of up) {
    for (const b of right) {
      if (overlapX(a, b)) lift = Math.max(lift, a.y + a.height + gap - b.y);
      if (overlapY(a, b)) pushRight = Math.max(pushRight, a.x + a.width + gap - b.x);
    }
    for (const b of left) {
      if (overlapX(a, b)) lift = Math.max(lift, a.y + a.height + gap - b.y);
      if (overlapY(a, b)) pushLeft = Math.max(pushLeft, b.x + b.width + gap - a.x);
    }
  }
  if (lift > 0 && Math.max(pushRight, pushLeft) <= lift) {
    for (const box of right) box.x += pushRight;
    for (const box of left) box.x -= pushLeft;
  } else if (lift > 0) {
    for (const box of up) box.y -= lift;
  }
  return boxes;
}
