import { WindowMinimise, WindowToggleMaximise, Quit } from '../../../wailsjs/runtime/runtime';

export function WindowControls() {
  return (
    <div className="flex items-center gap-2 w-32">
      <button
        onClick={Quit}
        className="w-3 h-3 rounded-full bg-[#ed6a5e] hover:brightness-110 transition-all"
        title="Close"
      />
      <button
        onClick={WindowMinimise}
        className="w-3 h-3 rounded-full bg-[#f5bf4f] hover:brightness-110 transition-all"
        title="Minimize"
      />
      <button
        onClick={WindowToggleMaximise}
        className="w-3 h-3 rounded-full bg-[#5bbf45] hover:brightness-110 transition-all"
        title="Maximize"
      />
    </div>
  );
}
