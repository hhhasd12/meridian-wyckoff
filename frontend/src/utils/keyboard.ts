export function setupKeyboard(
  setTool: (t: string) => void,
  undo: () => void,
  redo: () => void,
  del: () => void
) {
  const toolMap: Record<string, string> = {
    '1': 'cursor',
    '2': 'trend_line',
    '3': 'parallel_channel',
    '4': 'horizontal_line',
    '5': 'vertical_line',
    '6': 'callout',
    '7': 'phase_marker',
  };

  const handler = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

    if (toolMap[e.key]) {
      setTool(toolMap[e.key]);
      return;
    }

    if (e.key === 'Escape') setTool('cursor');

    if (e.key === 'Delete') del();

    if (e.ctrlKey && e.key === 'z') {
      e.preventDefault();
      undo();
    }

    if (e.ctrlKey && e.key === 'y') {
      e.preventDefault();
      redo();
    }
  };

  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}
