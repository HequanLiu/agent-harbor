import { API_URL } from "../api/config";
import { savedLoginStore } from "../core/saved-login";
import { credentialVault } from "./credential-vault";
export const savedLogin = savedLoginStore(credentialVault, API_URL);
