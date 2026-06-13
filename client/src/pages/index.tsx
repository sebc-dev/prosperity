import { createFileRoute } from '@tanstack/react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

// Showcase des primitives (AC : « un écran de démo »). Le <h1> est figé à
// « Composants » (couplage strict avec le regex /composants/i d'index.test).
function Showcase() {
  return (
    <Card className="mx-auto max-w-xl">
      <CardHeader>
        <CardTitle>
          <h1>Composants</h1>
        </CardTitle>
        <CardDescription>Primitives shadcn/ui en clair et sombre.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
        </div>

        <Input placeholder="Saisie…" aria-label="Champ de démo" />

        <div className="flex flex-wrap gap-2">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline">Ouvrir un dialog</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Dialog de démo</DialogTitle>
                <DialogDescription>
                  Une primitive Dialog (Radix) montée via le portail.
                </DialogDescription>
              </DialogHeader>
            </DialogContent>
          </Dialog>

          <Button onClick={() => toast.success('Toast de démo (Sonner)')}>
            Déclencher un toast
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export const Route = createFileRoute('/')({
  component: Showcase,
})
