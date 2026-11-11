/** Original Figma assets; intrinsic SVG dimensions remain unchanged. */
export function DeskIcon({ name }: { name: string }): React.JSX.Element {
    return <img className="desk-icon" src={`/figma/${name}.svg`} alt="" aria-hidden="true" />;
}
