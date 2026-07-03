export interface Resource {
  uri: string;
  title?: string;
  description?: string;
  /** @deprecated use uri */
  id?: string;
  /** @deprecated use title */
  name?: string;
}

