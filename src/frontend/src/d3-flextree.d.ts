// Minimal typings for d3-flextree (the package ships none).
declare module "d3-flextree" {
  export interface FlexNode<T> {
    data: T;
    x: number;
    y: number;
    children?: FlexNode<T>[];
    parent: FlexNode<T> | null;
    each(callback: (node: FlexNode<T>) => void): void;
  }
  export interface FlexLayout<T> {
    (root: FlexNode<T>): FlexNode<T>;
    hierarchy(data: T, children?: (d: T) => T[] | undefined): FlexNode<T>;
  }
  export function flextree<T>(options: {
    nodeSize: (node: FlexNode<T>) => [number, number];
    spacing?: number | ((a: FlexNode<T>, b: FlexNode<T>) => number);
    children?: (d: T) => T[] | undefined;
  }): FlexLayout<T>;
}
