import { useRef, useEffect, useState, useCallback } from "react";
import type { TileStatus } from "../types";

interface Props {
  grid: TileStatus[][];
  currentTile: { i: number; j: number; k: number } | null;
  kTotal: number;
}

const STATUS_COLORS: Record<TileStatus, string> = {
  pending: "#e0e0e0",
  in_flight: "#4299e1",
  completed: "#48bb78",
  failed: "#f56565",
};

const MAX_CELL = 48;
const MIN_CELL = 16;
const GAP = 2;

export function TileGrid({ grid, currentTile, kTotal }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  const handleResize = useCallback((entries: ResizeObserverEntry[]) => {
    for (const entry of entries) {
      setContainerWidth(entry.contentRect.width);
    }
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(handleResize);
    observer.observe(container);
    setContainerWidth(container.clientWidth);

    return () => observer.disconnect();
  }, [handleResize]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || grid.length === 0 || containerWidth === 0) return;

    const rows = grid.length;
    const cols = grid[0].length;

    const availableWidth = containerWidth - GAP;
    const rawCell = Math.floor((availableWidth - GAP) / cols) - GAP;
    const cellSize = Math.max(MIN_CELL, Math.min(MAX_CELL, rawCell));

    const dpr = window.devicePixelRatio || 1;
    const width = cols * (cellSize + GAP) + GAP;
    const height = rows * (cellSize + GAP) + GAP;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.scale(dpr, dpr);
    ctx.fillStyle = "#1a202c";
    ctx.fillRect(0, 0, width, height);

    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const x = GAP + j * (cellSize + GAP);
        const y = GAP + i * (cellSize + GAP);
        const status = grid[i][j];

        ctx.fillStyle = STATUS_COLORS[status];
        ctx.fillRect(x, y, cellSize, cellSize);

        // Show k progress for in-flight tile (only when cells >= 32px)
        if (
          cellSize >= 32 &&
          currentTile &&
          currentTile.i === i &&
          currentTile.j === j &&
          status === "in_flight"
        ) {
          ctx.fillStyle = "#fff";
          ctx.font = `bold ${Math.round(cellSize * 0.25)}px monospace`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(
            `k=${currentTile.k}/${kTotal}`,
            x + cellSize / 2,
            y + cellSize / 2
          );
        }

        // Show (i,j) label when cells >= 24px
        if (cellSize >= 24) {
          ctx.fillStyle = status === "pending" ? "#666" : "#fff";
          ctx.font = `${Math.round(cellSize * 0.2)}px monospace`;
          ctx.textAlign = "left";
          ctx.textBaseline = "top";
          ctx.fillText(`${i},${j}`, x + 3, y + 3);
        }
      }
    }
  }, [grid, currentTile, kTotal, containerWidth]);

  if (grid.length === 0) return null;

  return (
    <div className="tile-grid">
      <h3>Tile Progress</h3>
      <div className="legend">
        {(Object.entries(STATUS_COLORS) as [TileStatus, string][]).map(([status, color]) => (
          <span key={status} className="legend-item">
            <span className="swatch" style={{ background: color }} />
            {status.replace("_", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </span>
        ))}
      </div>
      <div ref={containerRef}>
        <canvas
          ref={canvasRef}
          role="img"
          aria-label="Tile progress grid showing status of each computation tile"
        />
      </div>
    </div>
  );
}
