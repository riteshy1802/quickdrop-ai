"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  ChevronDown,
  ChevronLeft,
  ChevronsLeft,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Search,
  ShieldCheck,
  Wallet,
  ScanSearch,
  ExternalLink,
} from "lucide-react";
import { DropdownMenu, Popover } from "radix-ui";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { Logo } from "@/components/shared/logo";
import { useOpsAuth, RequireOps } from "./auth-context";
import { useOpsAction, useOpsData } from "./use-ops";
const navigation = [
  { href: "/ops", label: "Overview", icon: LayoutDashboard },
  { href: "/ops/conversations", label: "Conversations", icon: MessageSquare },
  {
    href: "/ops/approvals",
    label: "Approvals & Escalations",
    icon: ShieldCheck,
  },
  { href: "/ops/payouts", label: "Payouts", icon: Wallet },
  { href: "/ops/audit", label: "Audit Logs", icon: ScanSearch },
];
function Sidebar({
  collapsed,
  onCollapse,
  onNavigate,
}: {
  collapsed: boolean;
  onCollapse: () => void;
  onNavigate?: () => void;
}) {
  const path = usePathname(),
    query = useOpsData(),
    auth = useOpsAuth();
  const pending =
    query.data?.cases.filter((c) => c.status === "PENDING").length ?? 0;
  const escalations =
    query.data?.cases.filter(
      (c) =>
        c.kind === "ESCALATION" && ["PENDING", "IN_REVIEW"].includes(c.status),
    ).length ?? 0;
  return (
    <div className="ops-sidebar-content">
      <div className="ops-brand">
        <Logo />
        <span>OPERATIONS CONSOLE</span>
      </div>
      <span className="ops-nav-label">WORKSPACE</span>
      <nav aria-label="Operations navigation">
        {navigation.map(({ href, label, icon: Icon }) => (
          <Link
            href={href}
            key={href}
            title={collapsed ? label : undefined}
            onClick={onNavigate}
            className={
              (href === "/ops" ? path === href : path.startsWith(href))
                ? "active"
                : ""
            }
          >
            <Icon size={17} />
            <span>{label}</span>
            {href === "/ops/approvals" && pending > 0 && <b>{pending}</b>}
          </Link>
        ))}
      </nav>
      {!collapsed && (
        <div className="ops-sidebar-status">
          <span className="ops-kicker">NEEDS ATTENTION</span>
          <Link href="/ops/approvals" onClick={onNavigate}>
            {escalations} active escalation{escalations === 1 ? "" : "s"}
            <span>View queue →</span>
          </Link>
        </div>
      )}
      <div className="ops-sidebar-bottom">
        <Link href="/rider">
          <ExternalLink size={14} />
          <span>Rider simulator</span>
        </Link>
        <button
          onClick={onCollapse}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronsLeft size={16} />
          <span>Collapse sidebar</span>
        </button>
        <div className="ops-operator">
          <span className="ops-avatar">DO</span>
          <span>
            <strong>{auth.user?.name}</strong>
            <small>Demo operator</small>
          </span>
        </div>
      </div>
    </div>
  );
}
function Topbar({ onMenu }: { onMenu: () => void }) {
  const path = usePathname(),
    auth = useOpsAuth(),
    query = useOpsData(),
    action = useOpsAction();
  const [search, setSearch] = useState("");
  const nav =
    navigation.find(
      (item) => item.href !== "/ops" && path.startsWith(item.href),
    ) ?? navigation[0];
  const id = path.split("/")[3];
  const unread = query.data?.notifications.filter((n) => !n.read).length ?? 0;
  const matches =
    query.data?.threads
      .filter((t) =>
        (
          t.conversation.id +
          " " +
          t.conversation.rider_id +
          " " +
          t.conversation.title
        )
          .toLowerCase()
          .includes(search.toLowerCase()),
      )
      .slice(0, 5) ?? [];
  return (
    <header className="ops-topbar">
      <Button
        variant="ghost"
        size="icon"
        className="ops-mobile-menu"
        aria-label="Open navigation"
        onClick={onMenu}
      >
        <Menu size={18} />
      </Button>
      <div className="ops-breadcrumb">
        <span>Operations</span>
        <ChevronLeft size={11} />
        <Link href={nav.href}>{nav.label}</Link>
        {id && (
          <>
            <span>/</span>
            <code>{id}</code>
          </>
        )}
      </div>
      <div className="ops-topbar-actions">
        <Popover.Root>
          <Popover.Trigger asChild>
            <Button variant="ghost" size="icon" aria-label="Search workspace">
              <Search size={17} />
            </Button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              className="ops-popover ops-search-popover"
              sideOffset={8}
              align="end"
            >
              <label className="ops-search">
                <Search size={14} />
                <input
                  autoFocus
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Rider or conversation ID"
                  aria-label="Search riders and conversations"
                />
              </label>
              <div className="ops-search-results">
                {matches.map((t) => (
                  <Popover.Close asChild key={t.conversation.id}>
                    <Link href={`/ops/conversations/${t.conversation.id}`}>
                      <strong>{t.conversation.title}</strong>
                      <span>
                        {t.conversation.rider_id} · {t.conversation.id}
                      </span>
                    </Link>
                  </Popover.Close>
                ))}
                {!matches.length && <p>No matching conversations.</p>}
              </div>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
        <Popover.Root>
          <Popover.Trigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="ops-notification-trigger"
              aria-label={`Notifications, ${unread} unread`}
            >
              <Bell size={17} />
              {unread > 0 && <i />}
            </Button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              className="ops-popover ops-notifications"
              sideOffset={8}
              align="end"
            >
              <h2>
                Notifications <span>{unread} unread</span>
              </h2>
              {query.data?.notifications.slice(0, 7).map((n) => (
                <div className={n.read ? "is-read" : ""} key={n.id}>
                  <Popover.Close asChild>
                    <Link
                      href={n.href}
                      onClick={() =>
                        action.mutate({ type: "read_notification", id: n.id })
                      }
                    >
                      <strong>{n.title}</strong>
                      <span>{n.detail}</span>
                    </Link>
                  </Popover.Close>
                  {!n.read && (
                    <button
                      aria-label={`Mark ${n.title} read`}
                      disabled={action.isPending}
                      onClick={() =>
                        action.mutate({ type: "read_notification", id: n.id })
                      }
                    >
                      Read
                    </button>
                  )}
                </div>
              ))}
              {action.error && <p role="alert">{action.error.message}</p>}
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
        <span className="ops-topbar-divider" />
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button className="ops-profile-trigger">
              <span className="ops-avatar">DO</span>
              <span className="ops-profile-name">Demo Operator</span>
              <ChevronDown size={12} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              className="ops-popover ops-operator-menu"
              align="end"
              sideOffset={10}
            >
              <DropdownMenu.Label>{auth.user?.email}</DropdownMenu.Label>
              <DropdownMenu.Separator />
              <DropdownMenu.Item onSelect={() => void auth.logout()}>
                <LogOut size={14} />
                Sign out of demo
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </header>
  );
}
export function OpsShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false),
    [mobile, setMobile] = useState(false);
  return (
    <RequireOps>
      <div className={`ops-console ${collapsed ? "is-collapsed" : ""}`}>
        <aside className="ops-sidebar">
          <Sidebar
            collapsed={collapsed}
            onCollapse={() => setCollapsed(!collapsed)}
          />
        </aside>
        <div className="ops-main">
          <Topbar onMenu={() => setMobile(true)} />
          <div className="ops-demo-strip">
            <span>DEMO WORKSPACE</span>
            <p>Sample records · No live payments or production authorization</p>
          </div>
          <main className="ops-page">{children}</main>
        </div>
        <Sheet open={mobile} onOpenChange={setMobile}>
          <SheetContent side="left" className="ops-nav-sheet">
            <SheetTitle className="sr-only">Operations navigation</SheetTitle>
            <SheetDescription className="sr-only">
              Navigate the demo operations workspace.
            </SheetDescription>
            <Sidebar
              collapsed={false}
              onCollapse={() => setMobile(false)}
              onNavigate={() => setMobile(false)}
            />
          </SheetContent>
        </Sheet>
      </div>
    </RequireOps>
  );
}
