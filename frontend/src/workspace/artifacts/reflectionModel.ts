export function reflectionRays(angle: number) {
  if (!Number.isInteger(angle) || angle < 0 || angle > 80) throw new RangeError('入射角须为 0–80 度的整数');
  const radians = angle * Math.PI / 180;
  const x = Math.sin(radians) * 140;
  const y = -Math.cos(radians) * 140;
  return { incident: { x: x === 0 ? 0 : -x, y }, reflected: { x, y }, reflectedAngle: angle };
}
