import Code from 'lucide-react/dist/esm/icons/code';
import Terminal from 'lucide-react/dist/esm/icons/terminal';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';

const PYTHON_SDK_GUIDE = 'https://github.com/OpenMined/syfthub/blob/main/docs/python/guides/sdk.md';

/**
 * Retirement notice at /cli-setup.
 *
 * The retired `syft` CLI opened this URL to finish its browser sign-in, expecting a page that
 * minted a token and handed it back to the binary. That flow is gone; the binary waits for a
 * token that never arrives, so this page tells the person why and where to go instead.
 */
export default function CliRetiredPage() {
  return (
    <div className='flex min-h-[60vh] flex-col items-center justify-center px-6 py-16'>
      <div className='text-center'>
        <div className='bg-muted mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full'>
          <Terminal className='text-muted-foreground h-10 w-10' />
        </div>

        <h1 className='font-rubik text-foreground mb-4 text-3xl font-semibold'>
          The syft CLI is retired
        </h1>

        <p className='font-inter text-muted-foreground mx-auto mb-4 max-w-md'>
          You got here because an old <code>syft</code> binary tried to sign in. That sign-in can no
          longer complete: the CLI is no longer maintained and this page no longer issues tokens.
          You can close the terminal that is waiting.
        </p>
        <p className='font-inter text-muted-foreground mx-auto mb-8 max-w-md'>
          The Python SDK replaces it. It searches sources, shows you the cost before anything is
          sent, and pays from your wallets.
        </p>

        <div className='flex flex-col items-center justify-center gap-3 sm:flex-row'>
          <Link to='/build'>
            <Button size='lg' className='font-inter'>
              <Code className='mr-2 h-4 w-4' />
              Get started with the Python SDK
            </Button>
          </Link>
          <a href={PYTHON_SDK_GUIDE} target='_blank' rel='noopener noreferrer'>
            <Button size='lg' variant='outline' className='font-inter'>
              Read the guide
            </Button>
          </a>
        </div>
      </div>
    </div>
  );
}
