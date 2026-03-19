import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2 } from 'lucide-react';
import { useAppStore, SETUP_COMPLETE_STATUS } from '@/stores/appStore';

function PromptForm() {
  const { setupFlow, respondToSetupPrompt } = useAppStore();
  const prompt = setupFlow.prompt;
  const [value, setValue] = useState('');

  useEffect(() => {
    setValue(prompt?.default || '');
  }, [prompt]);

  if (!prompt) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    respondToSetupPrompt(value);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <Label className="text-sm">{prompt.message}</Label>
      <Input
        type={prompt.secret ? 'password' : 'text'}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={prompt.placeholder || ''}
        autoFocus
        className="h-8 text-xs"
      />
      <div className="flex justify-end">
        <Button type="submit" size="sm">
          Continue
        </Button>
      </div>
    </form>
  );
}

function SelectForm() {
  const { setupFlow, respondToSetupSelect } = useAppStore();
  const selectEvt = setupFlow.select;
  const [selected, setSelected] = useState('');

  useEffect(() => {
    if (selectEvt?.options?.length) {
      setSelected(selectEvt.options[0].value);
    }
  }, [selectEvt]);

  if (!selectEvt) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    respondToSetupSelect(selected);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <Label className="text-sm">{selectEvt.message}</Label>
      <div className="space-y-1.5 max-h-48 overflow-y-auto">
        {selectEvt.options.map((opt) => (
          <label
            key={opt.value}
            className={`flex items-center gap-2 p-2 rounded border cursor-pointer text-xs transition-colors ${
              selected === opt.value
                ? 'border-primary bg-primary/5'
                : 'border-border hover:bg-muted/50'
            }`}
          >
            <input
              type="radio"
              name="setup-select"
              value={opt.value}
              checked={selected === opt.value}
              onChange={() => setSelected(opt.value)}
              className="accent-primary"
            />
            {opt.label || opt.value}
          </label>
        ))}
      </div>
      <div className="flex justify-end">
        <Button type="submit" size="sm">
          Continue
        </Button>
      </div>
    </form>
  );
}

function ConfirmForm() {
  const { setupFlow, respondToSetupConfirm } = useAppStore();
  const confirmEvt = setupFlow.confirm;

  if (!confirmEvt) return null;

  return (
    <div className="space-y-3">
      <p className="text-sm">{confirmEvt.message}</p>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => respondToSetupConfirm(false)}>
          No
        </Button>
        <Button size="sm" onClick={() => respondToSetupConfirm(true)}>
          Yes
        </Button>
      </div>
    </div>
  );
}

export function SetupFlowDialog() {
  const { setupFlow, cancelSetup, clearSetupFlow } = useAppStore();
  const { running, slug, status, error, prompt, select, confirm } = setupFlow;

  const isOpen =
    running || !!prompt || !!select || !!confirm || !!error || status === SETUP_COMPLETE_STATUS;
  const hasInteraction = !!prompt || !!select || !!confirm;
  const isComplete = status === SETUP_COMPLETE_STATUS && !running;

  const handleClose = () => {
    if (running) {
      cancelSetup();
    } else {
      clearSetupFlow();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle className="text-base">
            {isComplete ? 'Setup Complete' : `Setting up ${slug || 'endpoint'}...`}
          </DialogTitle>
          {status && !hasInteraction && !isComplete && (
            <DialogDescription className="text-xs">
              {status}
            </DialogDescription>
          )}
        </DialogHeader>

        {/* Error display */}
        {error && (
          <div className="p-2.5 bg-destructive/10 border border-destructive/20 rounded-md text-destructive text-xs">
            {error}
          </div>
        )}

        {/* Interactive forms */}
        {prompt && <PromptForm />}
        {select && <SelectForm />}
        {confirm && <ConfirmForm />}

        {/* Loading state when no interaction pending */}
        {running && !hasInteraction && !error && (
          <div className="flex items-center gap-3 py-4">
            <Loader2 className="animate-spin h-4 w-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Processing...</span>
          </div>
        )}

        {/* Complete state */}
        {isComplete && !error && (
          <div className="py-2">
            <p className="text-xs text-emerald-500">
              All setup steps completed successfully.
            </p>
          </div>
        )}

        <DialogFooter>
          {running && !hasInteraction && (
            <Button variant="outline" size="sm" onClick={() => cancelSetup()}>
              Cancel
            </Button>
          )}
          {!running && (
            <Button size="sm" onClick={handleClose}>
              {error ? 'Close' : 'Done'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
