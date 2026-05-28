# K3s Bootstrap

Ansible bootstrap for the SF single-node k3s VM at `40.76.107.241`.

## Host

- Azure VM: `screaming-lisbon`
- SSH: `adminuser@40.76.107.241`
- Private IP: `10.5.0.4`
- OS: Ubuntu 24.04 LTS, amd64
- Privilege: passwordless sudo

## Install

Run from this directory:

```bash
uvx --from ansible-core ansible-galaxy collection install -r requirements.yaml -p collections
uvx --from ansible-core ansible-playbook -i inventory.screaming-lisbon.yml k3s.orchestration.site
```

For a future multi-node cluster or externally managed join token, put the token in an ignored secret vars file and pass it with `-e`:

```yaml
# cluster.secret.yml
token: "<stable cluster token>"
```

```bash
uvx --from ansible-core ansible-playbook -i inventory.screaming-lisbon.yml -e @cluster.secret.yml k3s.orchestration.site
```

## Notes

- Local `ansible` is not required; the commands above use `uvx`.
- `api_endpoint` is the VM private IP because `k3s-ansible` checks control-plane readiness from the VM. Your Mac should use the `sf-k3s` context through the SSH tunnel instead.
- Port `6443` is not reachable publicly through Azure networking. Use an SSH tunnel for kubectl access unless the Azure NSG is intentionally opened to a restricted admin IP:

```bash
ssh -N -L 16443:127.0.0.1:6443 adminuser@40.76.107.241
kubectl config set-cluster k3s-ansible --server=https://127.0.0.1:16443
kubectl --context sf-k3s get nodes
```

- The k3s-ansible collection fetches kubeconfig to ignored local file `kubeconfig.screaming-lisbon`; it should not overwrite your global `~/.kube/config` on repeat runs.
