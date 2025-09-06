import { LineChart, Line } from 'recharts';

interface SparklineProps {
  data: { price: number }[];
  color?: string;
  width?: number;
  height?: number;
  ariaLabel?: string;
}

export default function Sparkline({
  data,
  color = '#8884d8',
  width = 100,
  height = 30,
  ariaLabel = 'Price trend',
}: SparklineProps) {
  return (
    <div role="img" aria-label={ariaLabel} tabIndex={0}>
      <LineChart
        width={width}
        height={height}
        data={data}
        margin={{ left: 0, right: 0, top: 0, bottom: 0 }}
      >
        <Line type="linear" dataKey="price" stroke={color} dot={false} />
      </LineChart>
    </div>
  );
}
