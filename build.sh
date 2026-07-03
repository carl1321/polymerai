#！/bin/bash
NAMESPACE=$1

if [[ ${NAMESPACE} == "polymerai" ]]
then 
    scp -r * gitlab-runner@122.51.104.121:/data/polymerai/deer_flow/
    ssh gitlab-runner@122.51.104.121 '
        export NVM_DIR="$HOME/.nvm"
        [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
        [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
        nvm use 24
        cd /data/polymerai/deer_flow/frontend
        pnpm build
        cd /data/polymerai/deer_flow
        pm2 restart ecosystem.config.js
    '
fi

pm2="/data/home/gitlab-runner/.nvm/versions/node/v24.14.0/bin/pm2"

if [[ ${NAMESPACE} == "main" ]]
then 
    scp -r * gitlab-runner@172.16.164.11:/data/ai_agent/deer_flow/
    ssh gitlab-runner@172.16.164.11 '
        export NVM_DIR="/usr/local/nvm"
        [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
        nvm use 24
        cd /data/ai_agent/deer_flow/frontend
        pnpm build
        cd /data/ai_agent/deer_flow 
        pm2 restart ecosystem.config.js
    '
fi

if [[ ${NAMESPACE} == "dev" ]]
then 
    scp -r * gitlab-runner@172.16.164.12:/data/ai_agent/deer_flow/
	ssh gitlab-runner@172.16.164.12 '
        export NVM_DIR="$HOME/.nvm"
        [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
        nvm use 24
        cd /data/ai_agent/deer_flow/frontend
        pnpm build
    '
	ssh gitlab-runner@172.16.164.12 "cd /data/ai_agent/deer_flow ; ${pm2} restart ecosystem.config.js"
fi
