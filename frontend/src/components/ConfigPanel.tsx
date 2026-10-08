interface Props {
  tileSize: number;
  onTileSizeChange: (size: number) => void;
}

export function ConfigPanel({ tileSize, onTileSizeChange }: Props) {
  return (
    <div className="config-panel">
      <h3>Configuration</h3>
      <label>
        Tile Size:
        <select
          value={tileSize}
          onChange={(e) => onTileSizeChange(parseInt(e.target.value, 10) || 256)}
        >
          <option value={128}>128 x 128</option>
          <option value={256}>256 x 256</option>
          <option value={512}>512 x 512</option>
          <option value={1024}>1024 x 1024</option>
          <option value={2048}>2048 x 2048</option>
        </select>
      </label>
    </div>
  );
}
