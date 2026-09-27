import { createContext, useContext, useState, type ReactNode } from "react";

// "Who" for the audit log. No authentication: a name typed in the header, kept in localStorage.
const KEY = "northpeak.actor";
const ActorContext = createContext<{ actor: string; setActor: (a: string) => void }>({
  actor: "",
  setActor: () => {},
});

function load(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function ActorProvider({ children }: { children: ReactNode }) {
  const [actor, setActorState] = useState(load);
  const setActor = (a: string) => {
    setActorState(a);
    try {
      localStorage.setItem(KEY, a);
    } catch {
      /* private mode: keep it in memory only */
    }
  };
  return <ActorContext.Provider value={{ actor, setActor }}>{children}</ActorContext.Provider>;
}

export const useActor = () => useContext(ActorContext);
