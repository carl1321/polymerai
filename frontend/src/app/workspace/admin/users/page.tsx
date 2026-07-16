"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { getToken } from "@/core/auth";
import {
  createUser,
  deleteUser,
  listUsers,
  updateUser,
  type CreateUserBody,
  type UserListItem,
  type UserListResponse,
} from "@/core/auth/admin-users-api";

export default function AdminUsersPage() {
  const router = useRouter();
  const [data, setData] = useState<UserListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [usernameFilter, setUsernameFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserListItem | null>(null);
  const [form, setForm] = useState<Partial<CreateUserBody> & { id?: string }>(
    {},
  );

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listUsers({
        page,
        page_size: pageSize,
        username: usernameFilter || undefined,
      });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load users");
      if (String(e).includes("401") || String(e).includes("403")) {
        router.push("/login");
      }
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, usernameFilter, router]);

  useEffect(() => {
    if (typeof window !== "undefined" && !getToken()) {
      router.push("/login");
      return;
    }
    fetchList();
  }, [fetchList, router]);

  async function handleCreate() {
    if (!form.username?.trim() || !form.email?.trim() || !form.password?.trim())
      return;
    try {
      await createUser({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        real_name: form.real_name?.trim(),
        phone: form.phone?.trim(),
        is_superuser: form.is_superuser ?? false,
        is_active: form.is_active ?? true,
      });
      setCreateOpen(false);
      setForm({});
      fetchList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    }
  }

  async function handleUpdate() {
    if (!editUser?.id) return;
    try {
      await updateUser(editUser.id, {
        email: form.email?.trim(),
        password: form.password ? form.password : undefined,
        real_name: form.real_name?.trim(),
        phone: form.phone?.trim(),
        is_superuser: form.is_superuser,
        is_active: form.is_active,
      });
      setEditUser(null);
      setForm({});
      fetchList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function handleDelete(user: UserListItem) {
    if (!confirm(`确定删除用户 "${user.username}"？`)) return;
    try {
      await deleteUser(user.id);
      fetchList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (typeof window !== "undefined" && !getToken()) {
    return null;
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>用户管理</CardTitle>
            <CardDescription>
              管理 DeerFlow 用户（需管理员登录）
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Input
              placeholder="按用户名筛选"
              value={usernameFilter}
              onChange={(e) => setUsernameFilter(e.target.value)}
              className="w-40"
            />
            <Button variant="outline" onClick={fetchList} disabled={loading}>
              查询
            </Button>
            <Button
              onClick={() => {
                setForm({});
                setCreateOpen(true);
              }}
            >
              新建用户
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && <p className="text-destructive mb-2 text-sm">{error}</p>}
          {loading ? (
            <p className="text-muted-foreground text-sm">加载中…</p>
          ) : data ? (
            <>
              <ScrollArea className="w-full">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="p-2 text-left">用户名</th>
                      <th className="p-2 text-left">邮箱</th>
                      <th className="p-2 text-left">姓名</th>
                      <th className="p-2 text-left">超级用户</th>
                      <th className="p-2 text-left">启用</th>
                      <th className="p-2 text-left">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((u) => (
                      <tr key={u.id} className="border-b">
                        <td className="p-2">{u.username}</td>
                        <td className="p-2">{u.email}</td>
                        <td className="p-2">{u.real_name ?? "—"}</td>
                        <td className="p-2">{u.is_superuser ? "是" : "否"}</td>
                        <td className="p-2">{u.is_active ? "是" : "否"}</td>
                        <td className="flex gap-2 p-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditUser(u);
                              setForm({
                                email: u.email,
                                real_name: u.real_name ?? "",
                                phone: u.phone ?? "",
                                is_superuser: u.is_superuser,
                                is_active: u.is_active,
                              });
                            }}
                          >
                            编辑
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            onClick={() => handleDelete(u)}
                          >
                            删除
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
              <div className="text-muted-foreground mt-2 flex items-center gap-4 text-sm">
                <span>共 {data.total} 条</span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page * pageSize >= data.total}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建用户</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <label className="text-sm">用户名 *</label>
            <Input
              value={form.username ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, username: e.target.value }))
              }
              placeholder="username"
            />
            <label className="text-sm">邮箱 *</label>
            <Input
              type="email"
              value={form.email ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, email: e.target.value }))
              }
              placeholder="user@example.com"
            />
            <label className="text-sm">密码 *</label>
            <Input
              type="password"
              value={form.password ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, password: e.target.value }))
              }
              placeholder="密码"
            />
            <label className="text-sm">姓名</label>
            <Input
              value={form.real_name ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, real_name: e.target.value }))
              }
              placeholder="可选"
            />
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_superuser ?? false}
                onChange={(e) =>
                  setForm((f) => ({ ...f, is_superuser: e.target.checked }))
                }
              />
              超级用户
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_active ?? true}
                onChange={(e) =>
                  setForm((f) => ({ ...f, is_active: e.target.checked }))
                }
              />
              启用
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button onClick={handleCreate}>创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog
        open={!!editUser}
        onOpenChange={(open) => !open && setEditUser(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑用户：{editUser?.username}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <label className="text-sm">邮箱 *</label>
            <Input
              type="email"
              value={form.email ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, email: e.target.value }))
              }
            />
            <label className="text-sm">新密码（不填则不修改）</label>
            <Input
              type="password"
              value={form.password ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, password: e.target.value }))
              }
              placeholder="留空保持原密码"
            />
            <label className="text-sm">姓名</label>
            <Input
              value={form.real_name ?? ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, real_name: e.target.value }))
              }
            />
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_superuser ?? false}
                onChange={(e) =>
                  setForm((f) => ({ ...f, is_superuser: e.target.checked }))
                }
              />
              超级用户
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_active ?? true}
                onChange={(e) =>
                  setForm((f) => ({ ...f, is_active: e.target.checked }))
                }
              />
              启用
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditUser(null)}>
              取消
            </Button>
            <Button onClick={handleUpdate}>保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
