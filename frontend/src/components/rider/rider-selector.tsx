"use client";
import { MapPin } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Rider } from "@/types/rider";
export function RiderSelector({
  riders,
  rider,
  onChange,
}: {
  riders: Rider[];
  rider: Rider;
  onChange: (id: string) => void;
}) {
  return (
    <div className="rider-identity">
      <span className="rider-overline">DEMO IDENTITY</span>
      <Select value={rider.id} onValueChange={onChange}>
        <SelectTrigger
          className="rider-selector"
          aria-label="Select demo rider"
        >
          <SelectValue>{rider.name}</SelectValue>
        </SelectTrigger>
        <SelectContent
          position="popper"
          align="start"
          sideOffset={7}
          className="rider-select-popover"
        >
          <SelectGroup>
            {riders.map((profile) => (
              <SelectItem
                className="rider-select-option"
                value={profile.id}
                key={profile.id}
                textValue={`${profile.name} ${profile.id} ${profile.city}`}
              >
                <span className="rider-select-avatar" aria-hidden="true">
                  {profile.name
                    .split(" ")
                    .map((part) => part[0])
                    .join("")}
                </span>
                <span className="rider-select-profile">
                  <strong>{profile.name}</strong>
                  <span>
                    {profile.city}
                    <code>{profile.id}</code>
                  </span>
                </span>
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
      <div className="rider-identity-meta">
        <MapPin size={11} />
        <span>{rider.city}</span>
        <code>{rider.id}</code>
      </div>
    </div>
  );
}
